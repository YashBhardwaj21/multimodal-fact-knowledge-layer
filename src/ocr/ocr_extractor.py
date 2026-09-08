"""OCR text extraction using Qwen3-VL vision-language model."""

import re
import logging
from pathlib import Path
from typing import Union, List, Optional, Dict, Tuple
from PIL import Image
import torch
from transformers import Qwen3VLForConditionalGeneration, AutoProcessor
from pdf2image import convert_from_path

logger = logging.getLogger(__name__)


class OCRExtractor:
    """Extract text from images and PDFs using Qwen3-VL vision-language model."""

    PAGE_SEPARATOR = "--- PAGE {page_num} ---"
    PAGE_SEPARATOR_PATTERN = r'---\s*PAGE\s*\d+\s*---'

    def __init__(
        self,
        model_name: str = "Qwen/Qwen3-VL-4B-Instruct",
        device: str = None,
        enable_preprocessing: bool = True,
        max_pages: int = None,
        use_flash_attention: bool = True
    ):
        self.model_name = model_name
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        self.enable_preprocessing = enable_preprocessing
        self.max_pages = max_pages

        has_flash_attn = False
        if use_flash_attention:
            try:
                import flash_attn
                has_flash_attn = True
            except ImportError:
                pass

        try:
            model_kwargs = {
                "device_map": "auto" if self.device == "cuda" else None,
            }

            if self.device == "cuda":
                model_kwargs["torch_dtype"] = torch.bfloat16
                if has_flash_attn and use_flash_attention:
                    model_kwargs["attn_implementation"] = "flash_attention_2"
            else:
                model_kwargs["torch_dtype"] = torch.float32

            self.model = Qwen3VLForConditionalGeneration.from_pretrained(
                self.model_name,
                **model_kwargs
            )

            if self.device == "cpu":
                self.model = self.model.to(self.device)

            self.model.eval()
            self.processor = AutoProcessor.from_pretrained(self.model_name)

        except Exception as e:
            logger.error(f"Failed to load Qwen3-VL model: {str(e)}")
            raise

    def _basic_text_cleanup(self, text: str) -> str:
        if not text:
            return ""

        text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)
        text = re.sub(r'!\[\]', '', text)
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'```[\w]*\n?', '', text)
        text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', text)
        text = re.sub(r'_{1,2}([^_]+)_{1,2}', r'\1', text)
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'\\([*_`#\[\]])', r'\1', text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text.strip()

    def _enhance_image_for_handwriting(self, image: Image.Image) -> Image.Image:
        try:
            from PIL import ImageEnhance

            if image.mode != 'RGB':
                image = image.convert('RGB')

            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(1.3)

            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(1.5)

            enhancer = ImageEnhance.Brightness(image)
            image = enhancer.enhance(1.05)

            return image

        except Exception as e:
            logger.warning(f"Image enhancement failed: {str(e)}")
            return image

    def is_pdf(self, file_path: Union[str, Path]) -> bool:
        return str(file_path).lower().endswith('.pdf')

    def _pdf_to_images(self, pdf_path: Union[str, Path]) -> List[Image.Image]:
        try:
            import fitz
            images = []
            pdf_document = fitz.open(str(pdf_path))

            for page_num in range(len(pdf_document)):
                page = pdf_document[page_num]
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                images.append(img)

            pdf_document.close()
            return images
        except ImportError:
            return convert_from_path(str(pdf_path), dpi=200)

    def _extract_from_image(
        self,
        image: Image.Image,
        enhance_handwriting: bool = True,
        custom_prompt: str = None
    ) -> str:
        if enhance_handwriting:
            image = self._enhance_image_for_handwriting(image)

        if image.mode != 'RGB':
            image = image.convert('RGB')

        try:
            prompt = custom_prompt or (
                "Extract all text from this image. Preserve the original text structure, line breaks, and formatting. "
                "Output only the extracted text without any additional commentary."
            )

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": prompt},
                    ],
                }
            ]

            inputs = self.processor.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_dict=True,
                return_tensors="pt"
            )
            inputs = inputs.to(self.model.device)

            with torch.no_grad():
                generated_ids = self.model.generate(
                    **inputs,
                    max_new_tokens=4096,
                    do_sample=False,
                    temperature=None,
                    top_p=None,
                )

            generated_ids_trimmed = [
                out_ids[len(in_ids):]
                for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
            ]

            result = self.processor.batch_decode(
                generated_ids_trimmed,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False
            )[0]

            if result and self.enable_preprocessing:
                result = self._basic_text_cleanup(result)

            return result.strip() if result else ""

        except Exception as e:
            logger.error(f"Extraction failed: {str(e)}")
            return ""

    def extract_text_from_pdf(
        self,
        pdf_path: Union[str, Path],
        return_pages_separately: bool = False
    ) -> Union[str, List[Dict]]:
        """Extract text from all pages in a PDF file."""
        try:
            images = self._pdf_to_images(pdf_path)
            total_pages = len(images)

            if self.max_pages and self.max_pages < total_pages:
                images = images[:self.max_pages]

            pages_data = []
            texts = []

            for i, image in enumerate(images):
                text = self._extract_from_image(image)

                if return_pages_separately:
                    pages_data.append({
                        'page_number': i + 1,
                        'text': text.strip() if text else "",
                        'has_content': bool(text and text.strip())
                    })

                if text and text.strip():
                    texts.append(f"{self.PAGE_SEPARATOR.format(page_num=i + 1)}\n{text.strip()}")

            if return_pages_separately:
                return pages_data

            return "\n\n".join(texts)

        except Exception as e:
            logger.error(f"PDF extraction failed: {str(e)}")
            return [] if return_pages_separately else ""

    def extract_text(
        self,
        image: Union[str, Path, Image.Image],
        return_metadata: bool = False,
        custom_prompt: str = None
    ) -> Union[str, Dict]:
        """Extract text from an image or PDF file."""
        metadata = {
            'source_type': 'unknown',
            'source_path': None,
            'pages': 1,
            'extraction_success': False
        }

        try:
            if isinstance(image, (str, Path)):
                metadata['source_path'] = str(image)

                if self.is_pdf(image):
                    metadata['source_type'] = 'pdf'
                    text = self.extract_text_from_pdf(image)
                    metadata['pages'] = len(re.findall(self.PAGE_SEPARATOR_PATTERN, text)) or 1
                else:
                    metadata['source_type'] = 'image'
                    image = Image.open(image).convert('RGB')
                    text = self._extract_from_image(image, custom_prompt=custom_prompt)
            elif isinstance(image, Image.Image):
                metadata['source_type'] = 'pil_image'
                text = self._extract_from_image(image, custom_prompt=custom_prompt)
            else:
                logger.error("Invalid image input type")
                text = ""

            metadata['extraction_success'] = bool(text and text.strip())
            metadata['char_count'] = len(text) if text else 0
            metadata['word_count'] = len(text.split()) if text else 0

            if return_metadata:
                return {'text': text, 'metadata': metadata}
            return text

        except Exception as e:
            logger.error(f"OCR extraction failed: {str(e)}")
            if return_metadata:
                return {'text': '', 'metadata': metadata}
            return ""

    def extract_from_file(self, image_path: Union[str, Path]) -> str:
        """Extract text from an image or PDF path."""
        return self.extract_text(image_path)

    def extract_from_multiple_images(
        self,
        image_paths: List[Union[str, Path]],
        return_metadata: bool = False
    ) -> List[Union[str, Dict]]:
        """Extract text from multiple images or PDFs."""
        results = []
        for image_path in image_paths:
            result = self.extract_text(image_path, return_metadata=return_metadata)
            results.append(result)
        return results

    def extract_batch(
        self,
        image_paths: List[Union[str, Path]],
        batch_size: int = 4
    ) -> List[str]:
        """Extract text from images in batches."""
        texts = []
        for i in range(0, len(image_paths), batch_size):
            batch_paths = image_paths[i:i + batch_size]
            for file_path in batch_paths:
                text = self.extract_text(file_path)
                texts.append(text)
        return texts

    def describe_image(self, image: Union[str, Path, Image.Image]) -> str:
        """Generate description of the image content."""
        if isinstance(image, (str, Path)):
            image = Image.open(image).convert('RGB')

        return self._extract_from_image(
            image,
            enhance_handwriting=False,
            custom_prompt="Describe what you see in this image in detail."
        )
