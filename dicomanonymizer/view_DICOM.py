"""
view DICOM images along with metadata
"""

import pydicom
import cv2
import os
import matplotlib.pyplot as plt
import argparse


#parse arguments
parser = argparse.ArgumentParser()
parser.add_argument("imgdir", type=str,
                    help="directory containing DICOM images. Subdirectories are allowed.")
args = parser.parse_args()


files = []
for r, d, f in os.walk(args.imgdir):
    for file in f:
        if '.dcm' in file:
            files.append(os.path.join(r, file))

print("We have total : " + str(len(files)) + " files")



for f in files:
    ds = pydicom.dcmread(f)

    print(ds)

    try:
        color_channel = ds.PhotometricInterpretation
        if 'MONOCHROME' in color_channel:
            img = cv2.cvtColor(ds.pixel_array, cv2.COLOR_GRAY2RGB)
        elif 'RGB' in color_channel:
            img = cv2.cvtColor(ds.pixel_array, cv2.COLOR_BGR2RGB)
        elif 'YBR' in color_channel:
            img = cv2.cvtColor(ds.pixel_array, cv2.COLOR_YCrCb2RGB)

        cv2.imshow('Press any key to continue.', img)
        cv2.waitKey(0)
        cv2.destroyAllWindows()


    except:
        print('Error accessing pixel data of image')

