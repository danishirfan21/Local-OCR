import streamlit as st
import easyocr
import numpy as np
from PIL import Image
import io
import base64
from streamlit_paste_button import paste_image_button as pbutton
import time
from PIL import ImageGrab

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

# Initialize session state
if 'pasted_image' not in st.session_state:
    st.session_state.pasted_image = None
if 'last_clipboard_check' not in st.session_state:
    st.session_state.last_clipboard_check = None
if 'auto_detect' not in st.session_state:
    st.session_state.auto_detect = True
if 'last_extracted_text' not in st.session_state:
    st.session_state.last_extracted_text = ""
if 'uploaded_file' not in st.session_state:
    st.session_state.uploaded_file = None
if 'auto_extract' not in st.session_state:
    st.session_state.auto_extract = True
if 'processing' not in st.session_state:
    st.session_state.processing = False
if 'last_processed_image' not in st.session_state:
    st.session_state.last_processed_image = None
if 'extracted_texts' not in st.session_state:
    st.session_state.extracted_texts = {}

# Sidebar settings
st.sidebar.title("⚙️ Settings")
auto_detect = st.sidebar.checkbox(
    "🔄 Auto-detect clipboard images",
    value=st.session_state.auto_detect,
    help="Automatically detect and process images copied to clipboard (e.g., from Snipping Tool)"
)
st.session_state.auto_detect = auto_detect

auto_extract = st.sidebar.checkbox(
    "⚡ Auto-extract text",
    value=st.session_state.auto_extract,
    help="Automatically extract text when a new image is detected"
)
st.session_state.auto_extract = auto_extract

if auto_detect:
    st.sidebar.success("✅ Monitoring clipboard...")
    st.sidebar.info("💡 Take a screenshot with Snipping Tool and it will be detected automatically!")
    
    # Check clipboard for images
    try:
        clipboard_image = ImageGrab.grabclipboard()
        if clipboard_image is not None and isinstance(clipboard_image, Image.Image):
            # Create a hash of the image to detect new images
            img_hash = hash(clipboard_image.tobytes())
            
            if st.session_state.last_clipboard_check != img_hash:
                st.session_state.last_clipboard_check = img_hash
                st.session_state.pasted_image = clipboard_image.copy()
                st.session_state.uploaded_file = None
                st.sidebar.success("🎉 New image detected!")
    except Exception as e:
        st.sidebar.error(f"Clipboard error: {str(e)}")

st.sidebar.markdown("---")
st.sidebar.markdown("### 📖 How to use:")
st.sidebar.markdown("""
1. **Auto-detect mode**: Enable the checkbox above, then take screenshots with Snipping Tool!

2. **Manual mode**: Upload a file or paste an image using the tabs below.
""")

# 3. Create tabs for different input methods
tab1, tab2 = st.tabs(["📁 Upload File", "📋 Paste Image"])

with tab1:
    # File Uploader UI
    uploaded_file = st.file_uploader("Choose an image...", type=["jpg", "jpeg", "png", "webp"])
    
    if uploaded_file is not None:
        st.session_state.uploaded_file = uploaded_file
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
            st.session_state.uploaded_file = None  # Clear uploaded file when pasting
        except Exception as e:
            st.error(f"Error processing pasted image: {e}")
    
    st.write("**Or manually upload an image:**")
    pasted_file = st.file_uploader("Upload image", type=["jpg", "jpeg", "png", "webp"], key="paste_upload")
    
    if pasted_file is not None:
        st.session_state.pasted_image = Image.open(pasted_file)
        st.session_state.uploaded_file = None  # Clear uploaded file when pasting

# Determine which image to process
image_to_process = None
if st.session_state.uploaded_file is not None:
    image_to_process = Image.open(st.session_state.uploaded_file)
elif st.session_state.pasted_image is not None:
    image_to_process = st.session_state.pasted_image

if image_to_process is not None:
    # Display the uploaded image
    image = image_to_process
    st.image(image, caption="Image to Process", width='stretch')
    
    # Create a unique hash for the current image to track if it's already been processed
    current_image_hash = hash(image.tobytes())
    
    # Auto-extract if enabled and this is a new image
    should_auto_extract = (
        st.session_state.auto_extract and 
        current_image_hash not in st.session_state.extracted_texts and
        not st.session_state.processing
    )
    
    # Button to trigger OCR or auto-extract
    if st.button("Extract Text") or should_auto_extract:
        st.session_state.processing = True
        
        with st.spinner("Processing image... (this may take a moment)"):
            try:
                # Convert PIL image to numpy array (required by EasyOCR)
                image_np = np.array(image)
                
                # Perform OCR
                results = reader.readtext(image_np)
                
                # Extract just the text from the results
                extracted_text = " ".join([text[1] for text in results])
                
                # Store extracted text for this specific image
                st.session_state.extracted_texts[current_image_hash] = extracted_text
                st.session_state.last_extracted_text = extracted_text
                st.session_state.processing = False
                
                if should_auto_extract:
                    st.success("✅ Text extracted automatically!")
                else:
                    st.success("Text extracted successfully!")
                
            except Exception as e:
                st.error(f"An error occurred: {e}")
                st.session_state.processing = False
    
    # Display extracted text if available for this image
    if current_image_hash in st.session_state.extracted_texts:
        extracted_text = st.session_state.extracted_texts[current_image_hash]
        st.markdown("### Extracted Text:")
        st.text_area("Result", extracted_text, height=200, key=f"extracted_text_{current_image_hash}")
        
        # Download button
        st.download_button(
            label="📥 Download Text",
            data=extracted_text,
            file_name="extracted_text.txt",
            mime="text/plain"
        )

# 4. Footer
st.markdown("---")
st.caption("Powered by EasyOCR and Streamlit")

# Auto-refresh when monitoring clipboard (at the end to avoid interference)
if st.session_state.auto_detect:
    time.sleep(1)
    st.rerun()