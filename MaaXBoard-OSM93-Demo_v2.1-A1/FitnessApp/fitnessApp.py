import cv2
import numpy as np
import mediapipe as mp
import math
import time
import sys


BICEP_CURL_POINTS = [11,13,15]
OVERHEAD_PRESSL_POINTS = [11,13,15]
SIDE_LATERAL_RAISE_POINTS = [23,11,13]

BICEP_CURL_ANGLE_RANGE = (210, 310)
OVERHEAD_PRESSL_ANGLE_RANGE = (70,140)
SIDE_LATERAL_RAISE_RANGE = (20, 75)

EXERCISE_1 = "Bicep Curls"
EXERCISE_2 = "Overhead Press"
EXERCISE_3 = "Side Lateral Raise"

ROM_RANGE = (0,100)
WIDTH_BOUND = 480
HEIGHT_BOUND = 640
CONF_THRESHOLD = 0.6

EXERCISE_REPS = 0
EXERCISE_SETS = 1

def init_fitness_app():
    global fitness_app
    fitness_app = FitnessAI()

class PoseDetector:
    def __init__(self):
        self.mpPose = mp.solutions.pose
        self.pose = self.mpPose.Pose()

    def detect_pose(self, frame):
        # Convert color BGR to RGB for inferencing
        imgRGB = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.pose.process(imgRGB)
        keypoint_list = []
        if results.pose_landmarks:
            for idx, landmark in enumerate(results.pose_landmarks.landmark):
                h, w, c = frame.shape
                confidence = landmark.visibility
                cx, cy = int(landmark.x * w), int(landmark.y*h)
                keypoint_list.append([idx, cx, cy, confidence])
        # print(keypoint_list)
        return keypoint_list

class Exercise:
    def __init__(self, name, keypoints, angle_range):
        self.name = name
        self.keypoints = keypoints
        self.rep_count = EXERCISE_REPS
        self.count = 0
        self.direction = 0
        self.rom = 0
        self.angle = 0
        self.set_count = EXERCISE_SETS
        self.rom_range = ROM_RANGE
        self.angle_range = angle_range
        self.status = None

    def check_keypoint_visibility(self, frame, kps):
        # keypoints from exercise, etc 11, 13, 15
        p1, p2, p3 = self.keypoints[0],self.keypoints[1],self.keypoints[2]

        # check that keypoints are valid in main list
        if kps[p1] or kps[p2] or kps[p3]:
            x1, y1, c1 = kps[p1][1:4]
            x2, y2, c2 = kps[p2][1:4]
            x3, y3, c3 = kps[p3][1:4]
            # check keypoint confidence scores against threshold
            # check keypoints are within the frame (bound w, h) - not added yet
            if (c1 < CONF_THRESHOLD or c2 < CONF_THRESHOLD or c3 < CONF_THRESHOLD):
                self.rom = 0
                self.status = "Difficulty Detecting Landmarks"
                return False
            else:
                self.status = "Good Landmark Detection"
                return True

    def draw_connections(self, img, p1, p2, p3):
        cv2.line(img, p1, p2, (255,255,255), 2)
        cv2.line(img, p2, p3, (255,255,255), 2)
        pass

    def calculate_angle(self, img, kps, draw=True):
        # print(self.keypoints)
        # print(kps)
        p1, p2, p3 = self.keypoints[0],self.keypoints[1],self.keypoints[2]

        # grab x,y for each keypoint
        x1, y1 = kps[p1][1:3]
        x2, y2 = kps[p2][1:3]
        x3, y3 = kps[p3][1:3]

        # calc angle of 3 points for ROM
        if self.name == EXERCISE_3: # side lateral
            self.angle = math.degrees(math.atan2(y1-y2, x1-x2)- math.atan2(y3-y2, x3-x2))
        else:
            self.angle = math.degrees(math.atan2(y3-y2, x3-x2) - math.atan2(y1-y2, x1-x2))
        self.angle = int(self.angle)

        if self.angle < 0:
            self.angle += 360

        # print(self.angle)
        if draw:
            cv2.circle(img, (x1,y1), 15, (0,0,255), 2)
            cv2.circle(img, (x1,y1), 5, (0,0,255), cv2.FILLED)
            cv2.circle(img, (x2,y2), 15, (0,0,255), 2)
            cv2.circle(img, (x2,y2), 5, (0,0,255), cv2.FILLED)
            cv2.circle(img, (x3,y3), 15, (0,0,255), 2)
            cv2.circle(img, (x3,y3), 5, (0,0,255), cv2.FILLED)
            # cv2.putText(img, str(self.angle), (x2-50, y2+50), cv2.FONT_HERSHEY_PLAIN, 2, (255,0,0), 2)

            self.draw_connections(img, (x1,y1),(x2,y2),(x3,y3))

    def calculate_rom(self):
        self.rom = int(np.interp(self.angle, self.angle_range, self.rom_range))
        # print("ROM: ", self.rom)

    def update_rep_count(self):
        # Update rep_count based on rom and direction
        if self.rom == 100:
            if self.direction == 0:
                self.count += 0.5
                self.direction = 1
        elif self.rom == 0:
            if self.direction == 1:
                self.count += 0.5
                self.direction = 0

        if self.count == 1:
            self.rep_count += 1
            self.count = 0

        # if self.rep_count == 0:
        #     if self.set_count > 0:
        #         # print("done w/ set")
        #         self.rep_count = EXERCISE_REPS
        #         self.set_count -= 1
        #     else:
        #         # print("done w/ ", self.name)
        #         pass

    def draw_progress_bar(self, image, x, y, width, height):
        cv2.rectangle(image, (1100, 100), (1175, 650), (0, 255, 0), 3)

        bar = np.interp(self.rom, (0, 100), (650, 100))
        cv2.rectangle(image, (1100, int(bar)), (1175, 650), (0, 255, 0), cv2.FILLED)
        pass

class FitnessAI:
    def __init__(self):
        self.pose_detector = PoseDetector()
        self.exercises = [
            Exercise("Bicep Curls", BICEP_CURL_POINTS, BICEP_CURL_ANGLE_RANGE),
            # Exercise("Overhead Press", OVERHEAD_PRESSL_POINTS, OVERHEAD_PRESSL_ANGLE_RANGE),
            # Exercise("Side Lateral Raise", SIDE_LATERAL_RAISE_POINTS, SIDE_LATERAL_RAISE_RANGE)
        ]
        self.current_exercise_index = 0

    def run_exercise_actions(self, exercise, frame, keypoint_list):
        # print("exercise name: ", exercise.name)
        # check all keypoints have good confidence
        if (exercise.check_keypoint_visibility(frame, keypoint_list)):
            exercise.calculate_angle(frame, keypoint_list)
            exercise.calculate_rom()
            exercise.update_rep_count()
            # exercise.draw_progress_bar(frame, None, None, None, None)


    def start(self, frame):
        keypoint_list = self.pose_detector.detect_pose(frame)
        exercise = self.exercises[self.current_exercise_index]
        if keypoint_list:
            self.run_exercise_actions(exercise, frame, keypoint_list)

            # cv2.imshow('frame', frame)

        # if exercise.set_count == 0 and exercise.rep_count == 0:
        #     # Move to the next exercise
        #     self.current_exercise_index = (self.current_exercise_index + 1) % len(self.exercises)
        # if self.all_exercises_completed():
        #     self.reset()

        # time.sleep(0.5)
        # cv2.imshow("frame", frame)
        return frame, exercise.rom, exercise.set_count, exercise.rep_count, exercise.name, exercise.status

    def reset(self):
        # Reset all exercise states
        for exercise in self.exercises:
            exercise.set_count = EXERCISE_SETS
            exercise.rep_count = EXERCISE_REPS
            exercise.count = 0
            exercise.direction = 0
        self.current_exercise_index = 0

    def all_exercises_completed(self):
        # Check if all exercises are completed
        # print("all exercises completed")
        return all(exercise.rep_count == 0 for exercise in self.exercises)


def process_frame_fitness(image):
    # image format when sending out - BGR
    # print("Fitness App Image Shape: ", image.shape)
    image_show, rom, set_count, rep_count, name, status = fitness_app.start(frame=image)
    return image_show, rom, set_count, int(rep_count), name, status

def reset_fitness_app():
    fitness_app.reset()


def fitness_app_exit():
    fitness_app = None

