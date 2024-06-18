import os
import requests
import base64
import streamlit as st
import numpy as np
from PIL import Image, ImageEnhance
import io
from pdf2image import convert_from_bytes

# Set environment variables from Streamlit secrets
os.environ["GOOGLE_OCR_API"] = st.secrets["GOOGLE_OCR_API"]
GOOGLE_OCR_API = os.getenv("GOOGLE_OCR_API")

def perform_ocr(image_content):
    url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_OCR_API}"
    image_base64 = base64.b64encode(image_content).decode('utf-8')
    request_data = {
        "requests": [
            {
                "image": {
                    "content": image_base64
                },
                "features": [
                    {
                        "type": "TEXT_DETECTION"
                    }
                ]
            }
        ]
    }
    response = requests.post(url, json=request_data)
    response_data = response.json()
    if 'error' in response_data:
        raise Exception(response_data['error']['message'])
    
    # Extract all text annotations
    texts = response_data['responses'][0].get('textAnnotations', [])
    if texts:
        full_text = texts[0]['description']
        return full_text
    return ""

def extract_mrz(text):
    lines = text.split('\n')
    mrz_line_1 = None
    mrz_line_2 = None
    
    for line in lines:
        if mrz_line_1 is None and line.startswith("P<"):
            mrz_line_1 = line
        elif mrz_line_1 is not None and mrz_line_2 is None and all(c.isalnum() or c == '<' for c in line):
            mrz_line_2 = line
            break

    if mrz_line_1 and mrz_line_2:
        return [mrz_line_1, mrz_line_2]
    return []

def extract_issuing_country(mrz_line):
    if mrz_line.startswith("P<") and len(mrz_line) > 3:
        return mrz_line[2:5]  # Extract 3 characters after "P<"
    return ""

def main():
    # Streamlit App
    st.title("Travelstruck Passport-o-Matic")
    st.header("Add picture of USA passport")
    st.subheader("Pic can be any orientation or any file format. But must be USA passport")
    image_file = st.file_uploader("Upload Image", type=['jpg', 'png', 'jpeg', 'pdf'])

    if image_file is not None:
        if image_file.type == "application/pdf":
            images = convert_from_bytes(image_file.read())
            img = images[0]  # Take the first page
        else:
            img = Image.open(image_file)
        
        # Enhance the brightness of the image
        brightness_enhancer = ImageEnhance.Brightness(img)
        img_brightened = brightness_enhancer.enhance(1.5)  # Increase brightness by a factor of 1.5

        # Enhance the contrast of the image
        contrast_enhancer = ImageEnhance.Contrast(img_brightened)
        img_contrasted = contrast_enhancer.enhance(1.5)  # Increase contrast by a factor of 1.5

        # Enhance the sharpness of the image
        sharpness_enhancer = ImageEnhance.Sharpness(img_contrasted)
        img_sharpened = sharpness_enhancer.enhance(2.0)  # Increase sharpness by a factor of 2
        
        img_array = np.array(img_sharpened)

        st.subheader('Image you Uploaded...')
        st.image(img_array, width=450)

        if st.button("Extract Text"):
            with st.spinner('Extracting...'):
                try:
                    # Perform OCR
                    # Convert the enhanced image to bytes for OCR
                    buffered = io.BytesIO()
                    img_sharpened.save(buffered, format="PNG")
                    img_sharpened_bytes = buffered.getvalue()
                    extracted_text = perform_ocr(img_sharpened_bytes)

                    # Extract and display the MRZ
                    mrz_lines = extract_mrz(extracted_text)
                    if mrz_lines:
                        issuing_country = extract_issuing_country(mrz_lines[0])
                        st.subheader('Issuing Country:')
                        st.text(issuing_country)
                        st.subheader('Extracted MRZ:')
                        st.text("\n".join(mrz_lines))
                    else:
                        st.error("MRZ not found in the extracted text.")
                except Exception as e:
                    st.error(f"Error: {e}")

if __name__ == "__main__":
    main()
