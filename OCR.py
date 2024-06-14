import os
import requests
import base64
import streamlit as st
import numpy as np
from PIL import Image, ImageEnhance

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
    texts = response_data['responses'][0].get('textAnnotations', [])
    return texts[0]['description'] if texts else ""

def main():
    # Streamlit App
    st.header("Add pic of passport or license below")
    st.subheader("For now, only jpg or png files. No pdf!")
    image_file = st.file_uploader("Upload Image", type=['jpg', 'png', 'jpeg', 'JPG'])

    if image_file is not None:
        img = Image.open(image_file)
        
        # Enhance the contrast of the image
        enhancer = ImageEnhance.Contrast(img)
        img_enhanced = enhancer.enhance(1.0)  # Increase contrast by a factor of 1
        
        img_array = np.array(img_enhanced)

        st.subheader('Image you Uploaded...')
        st.image(img_array, width=450)

        if st.button("Convert"):
            with st.spinner('Extracting Text from given Image...'):
                try:
                    # Perform OCR
                    image_content = img_enhanced.tobytes()
                    extracted_text = perform_ocr(image_content)

                    # Display the extracted text
                    st.subheader('Extracted Text:')
                    st.markdown(extracted_text)
                except Exception as e:
                    st.error(f"Error: {e}")

if __name__ == "__main__":
    main()
