import streamlit as st
import easyocr
import numpy as np
from PIL import Image
import io
import base64
from streamlit_paste_button import paste_image_button as pbutton

# 1. Set up the page configuration
st.set_page_config(page_title="Image Text Extractor", page_icon="📝")

st.title("📝 Image Text Extractor")
st.write("Upload an image or paste from clipboard, and this app will extract the text inside it.")

# 2. Initialize the EasyOCR Reader (loads the model into memory)
# We cache this resource so it doesn't reload every time you upload an image
@st.cache_resource
def load_reader():
    # 'en' for English. You can add other languages like ['en', 'fr']
    return easyocr.Reader(['en']) 

reader = load_reader()

# 3. Create tabs for different input methods
tab1, tab2 = st.tabs(["📁 Upload File", "📋 Paste Image"])

# Initialize session state for pasted image
if 'pasted_image' not in st.session_state:
    st.session_state.pasted_image = None

with tab1:
    # File Uploader UI
    uploaded_file = st.file_uploader("Choose an image...", type=["jpg", "jpeg", "png", "webp"])
    
    if uploaded_file is not None:
        image = Image.open(uploaded_file)
        st.session_state.pasted_image = None  # Clear pasted image when uploading
        
with tab2:
    st.write("📋 Click the button below, then use Ctrl+V (or Cmd+V on Mac) to paste an image from your clipboard:")
    
    # Paste button for clipboard images
    paste_result = pbutton(
        label="📋 Click here and paste image (Ctrl+V)",
        key="image_paste"
    )
    
    if paste_result.image_data is not None:
        try:
            # Convert the pasted image data to PIL Image
            st.session_state.pasted_image = paste_result.image_data
            uploaded_file = None  # Clear uploaded file when pasting
        except Exception as e:
            st.error(f"Error processing pasted image: {e}")
    
    st.write("**Or manually upload an image:**")
    pasted_file = st.file_uploader("Upload image", type=["jpg", "jpeg", "png", "webp"], key="paste_upload")
    
    if pasted_file is not None:
        st.session_state.pasted_image = Image.open(pasted_file)
        uploaded_file = None  # Clear uploaded file when pasting

# Determine which image to process
image_to_process = None
if uploaded_file is not None:
    image_to_process = Image.open(uploaded_file)
elif st.session_state.pasted_image is not None:
    image_to_process = st.session_state.pasted_image

if image_to_process is not None:
    # Display the uploaded image
    image = image_to_process
    st.image(image, caption="Image to Process", width='stretch')
    
    # Button to trigger OCR
    if st.button("Extract Text"):
        with st.spinner("Processing image... (this may take a moment)"):
            try:
                # Convert PIL image to numpy array (required by EasyOCR)
                image_np = np.array(image)
                
                # Perform OCR
                results = reader.readtext(image_np)
                
                # Extract just the text from the results
                extracted_text = " ".join([text[1] for text in results])
                
                # Display success and the text
                st.success("Text extracted successfully!")
                
                st.markdown("### Extracted Text:")
                st.text_area("Result", extracted_text, height=200)
                
            except Exception as e:
                st.error(f"An error occurred: {e}")

# 4. Footer
st.markdown("---")
st.caption("Powered by EasyOCR and Streamlit")