import math
import cv2
import numpy as np
#import tflite_runtime.interpreter as tflite
import tensorflow as tf

class PostureDetector:

    def __init__(self, model_path):
        self.interpreter = tf.lite.Interpreter(model_path=model_path)
        self.interpreter.allocate_tensors()
        self.input_idx = self.interpreter.get_input_details()[0]['index']
        self.input_shape = self.interpreter.get_input_details()[0]['shape'][1:3]

        outputs_idx_tmp = {}
        for output in self.interpreter.get_output_details():
            outputs_idx_tmp[output['name']] = output['index']

    def movenet(self, input_image):
        """Runs detection on an input image.

        Args:
        input_image: A [1, height, width, 3] tensor represents the input image
            pixels. Note that the height/width should already be resized and match the
            expected input resolution of the model before passing into this function.

        Returns:
        A [1, 1, 17, 3] float numpy array representing the predicted keypoint
        coordinates and scores.
        """
        # TF Lite format expects tensor type of uint8.
        #input_image = tf.lite.cast(input_image, dtype=tf.lite.uint8)


        # working solution:
        # 1.) grab expected input tensor dimensions for image
        # 2.) pre-process & resize the image with cv2
        # 3.) expand dimensions of the input_image array data to match tensor requirements
        dims = (self.input_shape[0], self.input_shape[1])
        input_image = cv2.resize(input_image, dims)
        input_image = np.expand_dims(input_image, axis=0)


        input_details = self.interpreter.get_input_details()
        output_details = self.interpreter.get_output_details()
        self.interpreter.set_tensor(input_details[0]['index'], input_image)
        # Invoke inference.
        self.interpreter.invoke()
        # Get the model prediction.
        keypoints_with_scores = self.interpreter.get_tensor(output_details[0]['index'])
        return keypoints_with_scores







