import os

# get current directory (dms folder)
current_dir = os.path.dirname(os.path.abspath(__file__))

# set as dms directory / models
model_dir = parent_dir = os.path.join(current_dir, "models-A1/")

MODEL_DIR = model_dir

CPU_MODELS = {
    'DETECT_MODEL': 'face_detection_front_128_full_integer_quant.tflite',
    'LANDMARK_MODEL': 'face_landmark_192_integer_quant.tflite',
    'EYE_MODEL': 'iris_landmark_quant.tflite',
    'YOLO_MODEL': 'yolov4_tiny_smk_call.tflite'
}

'''
08/27/2024
NPU models have been updated to support A1 Silicon
Previous A0 silicon did not require setting Ethos-U delegate to invoke the NPU. Appears that is required now.
'''

NPU_MODELS = {
    'DETECT_MODEL': 'face_detection_front_128_full_integer_quant_vela.tflite',
    'LANDMARK_MODEL': 'face_landmark_192_integer_quant_vela.tflite',
    'EYE_MODEL': 'iris_landmark_quant_vela.tflite',
    'YOLO_MODEL': 'yolov4_tiny_smk_call_vela.tflite'
}