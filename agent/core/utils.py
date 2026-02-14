from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import os
import tempfile
import textwrap
import boto3

class PageRenderer:
    # Proportional padding matching the frontend's 20px on an 800px canvas = 2.5%
    PADDING_RATIO = 20 / 800

    def __init__(self, page_width=1024, page_height=1536, frontend_canvas_w=800, frontend_canvas_h=1100):
        self.page_width = page_width
        self.page_height = page_height
        self.frontend_canvas_w = frontend_canvas_w
        self.frontend_canvas_h = frontend_canvas_h

        # Compute padding and inner area for the composite (proportional to frontend)
        self.pad_x = int(self.page_width * self.PADDING_RATIO)
        self.pad_y = int(self.page_height * self.PADDING_RATIO)
        self.inner_w = self.page_width - 2 * self.pad_x
        self.inner_h = self.page_height - 2 * self.pad_y

        # Frontend inner area (matching EditorCanvas: CANVAS_WIDTH - 40, PAGE_HEIGHT - 40)
        self.fe_inner_w = self.frontend_canvas_w - 40
        self.fe_inner_h = self.frontend_canvas_h - 40
        
        print(f"DEBUG: [PageRenderer] Init - Page: {page_width}x{page_height}, FE Canvas: {frontend_canvas_w}x{frontend_canvas_h}")
        print(f"DEBUG: [PageRenderer] Padding - pad_x: {self.pad_x}, pad_y: {self.pad_y}, inner: {self.inner_w}x{self.inner_h}")

    def create_composite_page(self, panels, include_balloons=False):
        """
        Crea un collage de los paneles basado en sus coordenadas de layout.
        Retorna la ruta a una imagen temporal.
        """
        # First pass: calculate required canvas size to fit all panels
        required_w = self.page_width
        required_h = self.page_height
        for panel in panels:
            layout = panel.get('layout')
            if not layout:
                continue
            px = int((layout['x'] / 100) * self.inner_w) + self.pad_x
            py = int((layout['y'] / 100) * self.inner_h) + self.pad_y
            pw = int((layout['w'] / 100) * self.inner_w)
            ph = int((layout['h'] / 100) * self.inner_h)
            required_w = max(required_w, px + pw)
            required_h = max(required_h, py + ph)

        print(f"DEBUG: [PageRenderer] Canvas size determined: {required_w}x{required_h}")
        canvas = Image.new('RGB', (required_w, required_h), color='white')
        
        for panel in panels:
            image_url = panel.get('image_url')
            layout = panel.get('layout')
            
            if not image_url or not layout:
                continue
                
            try:
                if image_url.startswith('http'):
                    import requests
                    response = requests.get(image_url, timeout=10)
                    panel_img = Image.open(BytesIO(response.content))
                else:
                    # Asumimos que es una llave de S3 (ej: generated/uuid.png)
                    s3 = boto3.client(
                        "s3",
                        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                        region_name=os.getenv("AWS_REGION")
                    )
                    bucket = os.getenv("AWS_STORAGE_BUCKET_NAME")
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_img:
                        tmp_img_path = tmp_img.name
                        tmp_img.close()  # Cierra el handle ANTES de descargar con s3.download_file
                        s3.download_file(bucket, image_url, tmp_img_path)
                    
                    with Image.open(tmp_img_path) as img:
                        panel_img = img.copy()  # Copia a memoria para cerrar el archivo inmediatamente
                    
                    try: os.remove(tmp_img_path)  # Limpiar temporal local
                    except: pass
                
                # Use the same formula as the frontend:
                # x = (layout.x / 100) * inner_w + pad_x
                x = int((layout['x'] / 100) * self.inner_w) + self.pad_x
                y = int((layout['y'] / 100) * self.inner_h) + self.pad_y
                w = int((layout['w'] / 100) * self.inner_w)
                h = int((layout['h'] / 100) * self.inner_h)

                panel_img = panel_img.resize((max(1, w), max(1, h)), Image.Resampling.LANCZOS)
                canvas.paste(panel_img, (x, y))

                if include_balloons:
                    self.draw_panel_balloons(canvas, panel, (x, y, w, h))
                
            except Exception as e:
                print(f"Error rendering panel {panel.get('id')}: {e}")
                
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
        tmp_path = tmp_file.name
        tmp_file.close()  # Cierra el handle para que Windows no lo bloquee
        
        try:
            canvas.save(tmp_path)
            return tmp_path
        except Exception as e:
            print(f"Error saving composite: {e}")
            if os.path.exists(tmp_path): os.remove(tmp_path)
            raise e

    def draw_panel_balloons(self, canvas, panel, panel_rect):
        """Dibuja los globos de un panel específico sobre el lienzo.
        
        Balloon coordinates from the frontend are RELATIVE TO THE PANEL GROUP.
        We scale them proportionally: composite_panel_size / frontend_panel_size.
        """
        draw = ImageDraw.Draw(canvas)
        px, py, pw, ph = panel_rect
        balloons = panel.get('balloons', [])
        layout = panel.get('layout', {})

        # Frontend panel dimensions in pixels (same formula as EditorCanvas.jsx)
        fe_panel_w = (layout.get('w', 30) / 100) * self.fe_inner_w
        fe_panel_h = (layout.get('h', 30) / 100) * self.fe_inner_h

        # Scale factors: composite panel pixels / frontend panel pixels
        scale_x = pw / fe_panel_w if fe_panel_w > 0 else 1
        scale_y = ph / fe_panel_h if fe_panel_h > 0 else 1
        
        print(f"DEBUG: [PageRenderer] Drawing balloons for Panel - px:{px}, py:{py}, pw:{pw}, ph:{ph}")
        print(f"DEBUG: [PageRenderer] Frontend Panel dimensions - fe_w:{fe_panel_w:.2f}, fe_h:{fe_panel_h:.2f}")
        print(f"DEBUG: [PageRenderer] Calculated Scale - sx:{scale_x:.4f}, sy:{scale_y:.4f}")

        for idx, b in enumerate(balloons):
            text = b.get('text', '')
            char = b.get('character', 'Narrador')
            pos_hint = b.get('position_hint', 'top-left')
            b_fontSize = b.get('fontSize', 13)  # Default matches frontend (EditorCanvas.jsx: fontSize || 13)

            # Scale font size proportionally
            scaled_fontSize = int(b_fontSize * scale_x)
            print(f"DEBUG: [PageRenderer] Balloon {idx} - fontSize (fe): {b_fontSize}, scaled: {scaled_fontSize} (using sx: {scale_x:.4f})")

            # Load font at the correct size
            try:
                # Expanded list of common font paths for both Windows and Linux
                font_paths = [
                    "arial.ttf", 
                    "C:\\Windows\\Fonts\\arial.ttf",
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
                    "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
                    "/usr/share/fonts/truetype/roboto/hinted/Roboto-Regular.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
                ]
                font = None
                for path in font_paths:
                    try:
                        font = ImageFont.truetype(path, scaled_fontSize)
                        small_font = ImageFont.truetype(path, max(8, int(scaled_fontSize * 0.7)))
                        print(f"DEBUG: [PageRenderer] Loaded font from: {path}")
                        break
                    except:
                        continue
                if not font:
                    print(f"WARNING: [PageRenderer] NO TrueType font found! Falling back to load_default (CANNOT SCALE). Checked: {font_paths}")
                    font = ImageFont.load_default()
                    small_font = ImageFont.load_default()
            except Exception as e:
                print(f"ERROR: [PageRenderer] Font loading error: {e}")
                font = ImageFont.load_default()
                small_font = ImageFont.load_default()

            # Determine balloon position and size
            has_stored_pos = b.get('x') is not None and b.get('y') is not None
            if has_stored_pos:
                # Scale from frontend panel-relative coords to composite panel-relative coords
                bx = px + int(b['x'] * scale_x)
                by = py + int(b['y'] * scale_y)
                bubble_w = int(b.get('width', 180) * scale_x)
                bubble_h = int(b.get('height', 70) * scale_y)
                print(f"DEBUG: [PageRenderer] Balloon {idx} Pos (fe) - x:{b['x']}, y:{b['y']} -> Composite - x:{bx}, y:{by}, w:{bubble_w}, h:{bubble_h}")
            else:
                # Fallback: use position_hint
                wrapped_text = textwrap.fill(text, width=25)
                try:
                    bbox = draw.textbbox((0, 0), wrapped_text, font=font)
                    text_w = bbox[2] - bbox[0]
                    text_h = bbox[3] - bbox[1]
                except:
                    text_w, text_h = draw.textsize(wrapped_text, font=font)

                padding = 15
                bubble_w = text_w + padding * 2
                bubble_h = text_h + padding * 2

                if pos_hint == 'top-left':
                    bx, by = px + 20, py + 20
                elif pos_hint == 'top-right':
                    bx, by = px + pw - bubble_w - 20, py + 20
                elif pos_hint == 'bottom-center':
                    bx, by = px + (pw - bubble_w) // 2, py + ph - bubble_h - 20
                else:
                    bx, by = px + 20, py + 20

            # Wrap text to fit bubble
            wrapped_text = textwrap.fill(text, width=max(10, int(bubble_w / (scaled_fontSize * 0.6))))

            # Draw bubble
            is_narration = b.get('type') == 'narration'
            bubble_rect = [bx, by, bx + bubble_w, by + bubble_h]
            if is_narration:
                draw.rectangle(bubble_rect, fill="#fef3c7", outline="black", width=2)
            else:
                draw.ellipse(bubble_rect, fill="white", outline="black", width=2)
            
            # Draw text centered in bubble
            padding = int(bubble_w * 0.08)
            draw.text((bx + padding, by + padding), wrapped_text, fill="black", font=font)

            # Character name
            if char and not is_narration:
                draw.text((bx + padding, by - int(scaled_fontSize * 0.8)), char.upper(), fill="purple", font=small_font)


