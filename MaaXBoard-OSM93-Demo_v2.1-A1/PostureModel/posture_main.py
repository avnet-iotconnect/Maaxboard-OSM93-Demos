#
# Copyright 2020-2022 NXP
#
# SPDX-License-Identifier: Apache-2.0
#
# More information on the model can be found here:
# https://colab.research.google.com/github/tensorflow/docs/blob/master/site/en/hub/tutorials/movenet.ipynb#scrollTo=zeGHgANcT7a1


import pathlib
import sys
import time
import argparse
import math
import cv2
import numpy as np
from PostureModel.posture_detect import PostureDetector

class posture_core:
    def __init__(self, cap, vela=False):
        if vela:
            self.MODEL_PATH = pathlib.Path("D:\Projects\93EVK\PostureModelWebServer\models")
            self.POSTURE_MODEL = "lite-model_movenet_singlepose_lightning_tflite_int8_4_vela.tflite"
        else:
            self.MODEL_PATH = pathlib.Path("D:\Projects\93EVK\PostureModelWebServer\models")
            self.POSTURE_MODEL = "lite-model_movenet_singlepose_lightning_tflite_int8_4.tflite"

        #self.cap = cap
        #ret, image = self.cap.read()
        #
        #if not ret:
        #    print("Can't read frame from cap device ")
        #    self.postureEnabled = False
        #else:
        #    self.postureEnabled = True
        self.postureEnabled = True

        # Dictionary that maps from joint names to keypoint indices.
        self.KEYPOINT_DICT = {
            'nose': 0,
            'left_eye': 1,
            'right_eye': 2,
            'left_ear': 3,
            'right_ear': 4,
            'left_shoulder': 5,
            'right_shoulder': 6,
            'left_elbow': 7,
            'right_elbow': 8,
            'left_wrist': 9,
            'right_wrist': 10,
            'left_hip': 11,
            'right_hip': 12,
            'left_knee': 13,
            'right_knee': 14,
            'left_ankle': 15,
            'right_ankle': 16
        }

        # Maps bones to a matplotlib color name.
        self.KEYPOINT_EDGE_INDS_TO_COLOR = {
            (0, 1): 'm',
            (0, 2): 'c',
            (1, 3): 'm',
            (2, 4): 'c',
            (0, 5): 'm',
            (0, 6): 'c',
            (5, 7): 'm',
            (7, 9): 'm',
            (6, 8): 'c',
            (8, 10): 'c',
            (5, 6): 'y',
            (5, 11): 'm',
            (6, 12): 'c',
            (11, 12): 'y',
            (11, 13): 'm',
            (13, 15): 'm',
            (12, 14): 'c',
            (14, 16): 'c'
        }

    def draw_connections(self, frame, keypoints, edges, confidence_threshold):
        y, x, c = frame.shape
        shaped = np.squeeze(np.multiply(keypoints, [y,x,1]))

        for edge, color in edges.items():
            p1, p2 = edge
            y1, x1, c1 = shaped[p1]
            y2, x2, c2 = shaped[p2]

            if (c1 > confidence_threshold) & (c2 > confidence_threshold):
                cv2.line(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0,0,255), 2)

    def draw_keypoints(self, frame, keypoints, confidence_threshold):
        y, x, c = frame.shape
        shaped = np.squeeze(np.multiply(keypoints, [y,x,1]))

        for kp in shaped:
            ky, kx, kp_conf = kp
            if kp_conf > confidence_threshold:
                cv2.circle(frame, (int(kx), int(ky)), 4, (0,255,0), -1)

    def main(self, image):
        posture_detector = PostureDetector(model_path=str((self.MODEL_PATH / self.POSTURE_MODEL)))
        keypoints = posture_detector.movenet(image)
        self.draw_connections(image, keypoints, self.KEYPOINT_EDGE_INDS_TO_COLOR, 0.3)
        self.draw_keypoints(image, keypoints, 0.3)
        return image


    def ProcessFrame(self, image):
        # detect single
        result = self.main(image)
        return result

    def GetFrame(self):
        ret, image = self.cap.read()

        if ret and np.any(image):
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            # detect single
            image_show = self.main(image)

            # put fps
            result = cv2.cvtColor(image_show, cv2.COLOR_RGB2BGR)

            return result
        else: return None

    def Close(self):
        time.sleep(2)
        self.cap.release()
        cv2.destroyAllWindows()
