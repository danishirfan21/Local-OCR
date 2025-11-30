# 📝 Image Text Extractor

A powerful and user-friendly OCR (Optical Character Recognition) application built with Streamlit and EasyOCR. Extract text from images with ease using a simple web interface.

![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Streamlit](https://img.shields.io/badge/streamlit-1.51.0-red.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## ✨ Features

- 📁 **File Upload** - Upload images in multiple formats (JPG, JPEG, PNG, WEBP)
- 📋 **Clipboard Paste** - Paste images directly from your clipboard
- 🔍 **Accurate OCR** - Powered by EasyOCR for reliable text extraction
- 🎨 **Clean UI** - Intuitive Streamlit interface
- ⚡ **Fast Processing** - Quick text extraction with visual feedback

## 🚀 Getting Started

### Prerequisites

- Python 3.8 or higher
- pip package manager

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/image-text-extractor.git
   cd image-text-extractor
   ```

2. **Create a virtual environment** (recommended)
   ```bash
   python -m venv .venv
   ```

3. **Activate the virtual environment**
   - Windows:
     ```bash
     .venv\Scripts\activate
     ```
   - macOS/Linux:
     ```bash
     source .venv/bin/activate
     ```

4. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

### Usage

1. **Run the application**
   ```bash
   streamlit run ocr_app.py
   ```

2. **Open your browser**
   - The app will automatically open at `http://localhost:8501`
   - If it doesn't, navigate to the URL manually

3. **Extract text from images**
   - **Option 1**: Use the "Upload File" tab to select an image from your computer
   - **Option 2**: Use the "Paste Image" tab to paste an image from your clipboard
   - Click "Extract Text" to process the image
   - Copy or download the extracted text

## 📦 Dependencies

- **streamlit** - Web application framework
- **easyocr** - OCR engine for text extraction
- **numpy** - Numerical computing library
- **pillow** - Image processing library
- **streamlit-paste-button** - Clipboard paste functionality
- **torch** - Deep learning framework (EasyOCR dependency)
- **opencv-python-headless** - Computer vision library

## 🛠️ Technical Details

### Supported Image Formats
- JPEG/JPG
- PNG
- WEBP

### OCR Languages
Currently configured for English text extraction. Additional languages can be added by modifying the EasyOCR Reader initialization:

```python
reader = easyocr.Reader(['en', 'es', 'fr'])  # English, Spanish, French
```

### Performance Notes
- The application uses CPU by default
- For faster processing, GPU acceleration can be utilized if CUDA or MPS is available
- First-time model download may take a few moments

## 📁 Project Structure

```
image-text-extractor/
├── ocr_app.py              # Main application file
├── requirements.txt        # Python dependencies
├── .gitignore             # Git ignore rules
└── README.md              # Project documentation
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- [EasyOCR](https://github.com/JaidedAI/EasyOCR) - For the powerful OCR engine
- [Streamlit](https://streamlit.io/) - For the amazing web framework
- [streamlit-paste-button](https://github.com/radzak/streamlit-paste-button) - For clipboard functionality

## 📧 Contact

For questions or feedback, please open an issue on GitHub.

---

Made with ❤️ using Streamlit and EasyOCR
