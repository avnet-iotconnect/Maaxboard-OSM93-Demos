#
# Copyright 2020-2023 NXP
#
# SPDX-License-Identifier: Apache-2.0
#

import pathlib
import sys
import time
import cv2

from dms import model_paths
from dms.face_detection import FaceDetector
from dms.eye_landmark import EyeMesher
from dms.face_landmark import FaceMesher
from dms.utils import *
from dms.inference_timer import InferenceTimeLogger
from dms.smoking_calling_yolov4 import SmokingCallingDetector

BAD_FACE_PENALTY = 0.01
""" % to remove for far away face """

NO_FACE_PENALTY = 0.7
""" % to remove for no faces in frame """

YAWN_PENALTY = 7.0
""" % to remove for yawning """

DISTRACT_PENALTY = 2.0
""" % to remove for looking away """

SLEEP_PENALTY = 5.0
""" % to remove for sleeping """

SMK_PENALTY = 2.0
""" % to remove for smoking """

CALL_PENALTY = 2.0
""" % to remove for calling """

RESTORE_CREDIT = -5.0
""" % to restore for doing everything right """

SMK_CALL_THRESHOLD = 0.7
""" The threshold value for smoking/calling detection """


class DMSManager:
    def __init__(self, run_on_hardware=False, use_npu=False):
        self.run_on_hardware = run_on_hardware
        self.use_npu = use_npu
        self.path_to_models = model_paths.MODEL_DIR
        self.face_detector = None
        self.face_mesher = None
        self.eye_mesher = None
        self.target_dim = (320,240)
        self.attention_status = None
        self.yawning_status = None
        self.eye_status = None
        self.inference_speed = None
        self.face_in_frame = False
        self.safe_value = 0
        self.phone_detected = True
        self.inference_logger = InferenceTimeLogger()
        self.platform = "i.MX93"

        model_selector = model_paths.NPU_MODELS if self.use_npu else model_paths.CPU_MODELS
        DELEGATE_PATH = "/usr/lib/libethosu_delegate.so" if self.use_npu else None

        self.face_detector = FaceDetector(model_path = str(self.path_to_models + model_selector['DETECT_MODEL']),
                                          delegate_path = DELEGATE_PATH,
                                          img_size=self.target_dim,
                                          run_on_hardware=self.run_on_hardware)

        self.face_mesher = FaceMesher(model_path=str((self.path_to_models + model_selector['LANDMARK_MODEL'])),
                                      delegate_path = DELEGATE_PATH,
                                      run_on_hardware=self.run_on_hardware)

        self.eye_mesher = EyeMesher(model_path=str((self.path_to_models + model_selector['EYE_MODEL'])),
                                    delegate_path = DELEGATE_PATH,
                                    run_on_hardware=self.run_on_hardware)

        inf_device = "NPU"
        self.smoking_calling_detector = SmokingCallingDetector(str((self.path_to_models + model_selector['YOLO_MODEL'])), inf_device, self.platform, conf=SMK_CALL_THRESHOLD)

    def draw_face_box(self, image, bboxes, landmarks, scores):
        for bbox, landmark, score in zip(bboxes.astype(int), landmarks.astype(int), scores):
            image = cv2.rectangle(image, tuple(bbox[:2]), tuple(bbox[2:]), color=(255, 0, 0), thickness=1)
            landmark = landmark.reshape(-1, 2)

            score_label = "{:.2f}".format(score)
            (label_width, label_height), baseline = cv2.getTextSize(score_label,
                                                                    cv2.FONT_HERSHEY_SIMPLEX,
                                                                    fontScale=0.2,
                                                                    thickness=1)
            label_btmleft = bbox[:2].copy() + 10
            label_btmleft[0] += label_width
            label_btmleft[1] += label_height
            cv2.rectangle(image, tuple(bbox[:2]), tuple(label_btmleft), color=(255, 0, 0), thickness=cv2.FILLED)
            cv2.putText(image, score_label, (bbox[0] + 5, label_btmleft[1] - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, fontScale=0.2, color=(255, 255, 255), thickness=1)
        return image

    # detect single frame
    def process_frame_dms(self, image):
        # distraction variables for penalty
        attention = False
        yawn = False
        sleep = False


        h, w, _ = image.shape
        # print("DMS image shape", image.shape)

        target_dim = max(w, h)
        padded_size = [(target_dim - h) // 2, (target_dim - h + 1) // 2,
                    (target_dim - w) // 2, (target_dim - w + 1) // 2]
        padded = cv2.copyMakeBorder(image.copy(),
                                    *padded_size,
                                    cv2.BORDER_CONSTANT,
                                    value=[0, 0, 0])
        padded = cv2.flip(padded, 3)

        try:
            #print("run call model")
            call_result = self.smoking_calling_detector.inference(image, False)
            if len(call_result != 0):
                self.phone_detected = True
            else:
                self.phone_detected = False


            #print("call result: ", call_result)

        except:
            print("error")

        # face detection
        bboxes_decoded, landmarks, scores = self.face_detector.inference(padded)

        self.inference_logger.calculate_total_model_averages()
        model_avgs = self.inference_logger.get_models_inf_average()
        self.inference_speed = "{:.2f}".format(model_avgs*1000)

        mesh_landmarks_inverse = []
        r_vecs, t_vecs = [], []

        for i, (bbox, landmark) in enumerate(zip(bboxes_decoded, landmarks)):
            # landmark detection
            aligned_face, M, angel = self.face_detector.align(padded, landmark)
            mesh_landmark, mesh_scores = self.face_mesher.inference(aligned_face)
            mesh_landmark_inverse = self.face_detector.inverse(mesh_landmark, M)
            mesh_landmarks_inverse.append(mesh_landmark_inverse)

            # pose detection
            r_vec, t_vec = self.face_detector.decode_pose(landmark)
            r_vecs.append(r_vec)
            t_vecs.append(t_vec)

        # draw
        image_show = padded.copy()
        self.draw_face_box(image_show, bboxes_decoded, landmarks, scores)
        for i, (mesh_landmark, r_vec, t_vec) in enumerate(zip(mesh_landmarks_inverse, r_vecs, t_vecs)):
            mouth_ratio = get_mouth_ratio(mesh_landmark, image_show)
            left_box, right_box = get_eye_boxes(mesh_landmark, padded.shape)

            left_eye_img = padded[left_box[0][1]:left_box[1][1], left_box[0][0]:left_box[1][0]]
            right_eye_img = padded[right_box[0][1]:right_box[1][1], right_box[0][0]:right_box[1][0]]

            if np.any(left_eye_img) == False or np.any(right_eye_img) == False:
                break

            left_eye_landmarks, left_iris_landmarks = self.eye_mesher.inference(left_eye_img)
            right_eye_landmarks, right_iris_landmarks = self.eye_mesher.inference(right_eye_img)


            # Adds boxes around the eyes
            # cv2.rectangle(image_show, left_box[0], left_box[1], color=(255, 0, 0), thickness=2)
            # cv2.rectangle(image_show, right_box[0], right_box[1], color=(255, 0, 0), thickness=2)


            left_eye_ratio = get_eye_ratio(left_eye_landmarks, image_show, left_box[0])
            right_eye_ratio = get_eye_ratio(right_eye_landmarks, image_show, right_box[0])

            pitch, roll, yaw = get_face_angle(r_vec, t_vec)
            iris_ratio = get_iris_ratio(left_iris_landmarks, right_iris_landmarks)

            if mouth_ratio > 0.2:
                self.yawning_status = True
                yawn = True
            else:
                self.yawning_status = False
                yawn = False

            if left_eye_ratio < 0.25 and right_eye_ratio < 0.25:
                self.eye_status = True
                sleep = True
            else:
                self.eye_status = False
                sleep = False

            if yaw > 15 and iris_ratio > 1.15:
                self.attention_status = "Left"
                attention = False

            elif yaw < -15 and iris_ratio < 0.85:
                self.attention_status = "Right"
                attention = False

            elif pitch > 30:
                self.attention_status = "Up"
                attention = False

            elif pitch < -13:
                self.attention_status = "Down"
                attention = False

            else:
                self.attention_status = "Forward"
                attention = True

        if not attention:
            self.safe_value = min(self.safe_value + DISTRACT_PENALTY, 100.00)
        if sleep:
            self.safe_value = min(self.safe_value + SLEEP_PENALTY, 100.00)
        if yawn:
            self.safe_value = min(self.safe_value + YAWN_PENALTY, 100.00)
        # if not face_cords:
        #     self.safe_value = min(self.safe_value + NO_FACE_PENALTY, 100.00)
        if attention and not self.eye_status and not self.yawning_status:
            # print("credit store")
            self.safe_value = max(self.safe_value + RESTORE_CREDIT, 0.00)

        # remove pad
        image_show = image_show[padded_size[0]:target_dim - padded_size[1], padded_size[2]:target_dim - padded_size[3]]
        image_show = cv2.flip(image_show, 1)
        return image_show, self.attention_status, self.yawning_status, self.eye_status, self.inference_speed, self.safe_value, self.phone_detected

