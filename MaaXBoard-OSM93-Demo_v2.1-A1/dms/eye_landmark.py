#
# Copyright 2020-2022 NXP
#
# SPDX-License-Identifier: Apache-2.0
#

import math
import cv2
import numpy as np
import time
from dms.inference_timer import InferenceTimeLogger

# IOTCONNECT Demo Modification
# pass an Ethos-U delegate timeout and options into every DMS model that uses the NPU
def _make_ethosu_delegate_path(delegate_path, tflite):
    import os
    opts = {
        "device_name": "/dev/ethosu0",
        "cache_file_path": ".",
        "timeout": int(os.getenv("ETHOSU_TIMEOUT_NS", "5000000000")),
        "enable_cycle_counter": 0,
        "enable_profiling": 0,
    }
    return tflite.load_delegate(delegate_path, options=opts)


class EyeMesher:
    EYE_KEY_NUM = 71
    IRIS_KEY_NUM = 5

    def __init__(self, model_path, delegate_path, run_on_hardware=False):

        self.inference_logger = InferenceTimeLogger()
    
        if run_on_hardware:
            import tflite_runtime.interpreter as tflite
        else:
            import tensorflow.lite as tflite
        
        if(delegate_path):
            # IOTCONNECT Demo Modification
            # pass an Ethos-U delegate timeout and options into every DMS model that uses the NPU
            ext_delegate = [_make_ethosu_delegate_path(delegate_path, tflite) if ('ethosu' in str(delegate_path)) else tflite.load_delegate(delegate_path)]
            self.interpreter = tflite.Interpreter(model_path=model_path, experimental_delegates=ext_delegate)
        else:
            self.interpreter = tflite.Interpreter(model_path=model_path)

        self.interpreter.allocate_tensors()
        self.input_idx = self.interpreter.get_input_details()[0]['index']
        self.input_shape = self.interpreter.get_input_details()[0]['shape'][1:3]

        outputs_idx_tmp = {}
        for output in self.interpreter.get_output_details():
            outputs_idx_tmp[output['name']] = output['index']
        self.outputs_idx = {'eye': outputs_idx_tmp['output_eyes_contours_and_brows:0'],
                'iris': outputs_idx_tmp['output_iris:0']}

    def inference(self, image):
        h, w = self.input_shape

        image_ = cv2.resize(image, tuple(self.input_shape)).astype(np.float32)
        image_ = (image_) / 255.0
        if len(image_.shape) < 4:
            image_ = image_[None, ...]

        # invoke
        self.interpreter.set_tensor(self.input_idx, image_)
        start = time.time()
        self.interpreter.invoke()
        end = time.time()
        delta = end-start
        self.inference_logger.iris_inf_time = delta
        # print("IRIS inference time:", delta)

        eye_landmarks = self.interpreter.get_tensor(self.outputs_idx['eye'])
        iris_landmarks = self.interpreter.get_tensor(self.outputs_idx['iris'])

        # postprocessing
        eye_landmarks = eye_landmarks.reshape(self.EYE_KEY_NUM, 3)
        eye_landmarks[:, 0] /= w
        eye_landmarks[:, 1] /= h
        eye_landmarks[:, 0] *= image.shape[1]
        eye_landmarks[:, 1] *= image.shape[0]

        iris_landmarks = iris_landmarks.reshape(self.IRIS_KEY_NUM, 3)
        iris_landmarks[:, 0] /= w
        iris_landmarks[:, 1] /= h
        iris_landmarks[:, 0] *= image.shape[1]
        iris_landmarks[:, 1] *= image.shape[0]

        # print("eye landmarks/iris", eye_landmarks, iris_landmarks)
        return eye_landmarks, iris_landmarks


