import requests
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import os
import tempfile
import textwrap

class PageRenderer:
    def __init__(self, page_width=1024, page_height=1536):
        self.page_width = page_width
        self.page_height = page_height

    def create_composite_page(self, panels, include_balloons=False):
        """
        Crea un collage de los paneles basado en sus coordenadas de layout.
        Retorna la ruta a una imagen temporal.
        """
        canvas = Image.new('RGB', (self.page_width, self.page_height), color='white')
        
        for panel in panels:
            image_url = panel.get('image_url')
            layout = panel.get('layout')
            
            if not image_url or not layout:
                continue
                
            try:
                response = requests.get(image_url, timeout=10)
                panel_img = Image.open(BytesIO(response.content))
                
                x = int((layout['x'] / 100) * self.page_width)
                y = int((layout['y'] / 100) * self.page_height)
                w = int((layout['w'] / 100) * self.page_width)
                h = int((layout['h'] / 100) * self.page_height)
                
                panel_img = panel_img.resize((w, h), Image.Resampling.LANCZOS)
                canvas.paste(panel_img, (x, y))

                if include_balloons:
                    self.draw_panel_balloons(canvas, panel, (x, y, w, h))
                
            except Exception as e:
                print(f"Error rendering panel {panel.get('id')}: {e}")
                
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
        canvas.save(tmp_file.name)
        return tmp_file.name

    def draw_panel_balloons(self, canvas, panel, panel_rect):
        """Dibuja los globos de un panel específico sobre el lienzo"""
        draw = ImageDraw.Draw(canvas)
        px, py, pw, ph = panel_rect
        balloons = panel.get('balloons', [])

        # Intentar cargar una fuente de sistema (Windows)
        try:
            # Caminos comunes para fuentes
            font_paths = ["arial.ttf", "C:\\Windows\\Fonts\\arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
            font = None
            for path in font_paths:
                try:
                    font = ImageFont.truetype(path, 18)
                    small_font = ImageFont.truetype(path, 14)
                    break
                except:
                    continue
            if not font:
                font = ImageFont.load_default()
                small_font = ImageFont.load_default()
        except:
            font = ImageFont.load_default()
            small_font = ImageFont.load_default()

        for b in balloons:
            text = b.get('text', '')
            char = b.get('character', 'Narrador')
            pos_hint = b.get('position_hint', 'top-left')
            
            # Envolver texto
            wrapped_text = textwrap.fill(text, width=25)
            
            # Calcular tamaño de texto
            try:
                bbox = draw.textbbox((0, 0), wrapped_text, font=font)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
            except:
                # Fallback para versiones viejas de Pillow
                text_w, text_h = draw.textsize(wrapped_text, font=font)

            padding = 15
            bubble_w = text_w + padding * 2
            bubble_h = text_h + padding * 2
            
            # Posicionamiento simplificado
            if pos_hint == 'top-left':
                bx, by = px + 20, py + 20
            elif pos_hint == 'top-right':
                bx, by = px + pw - bubble_w - 20, py + 20
            elif pos_hint == 'bottom-center':
                bx, by = px + (pw - bubble_w) // 2, py + ph - bubble_h - 20
            else:
                bx, by = px + 20, py + 20

            # Dibujar burbuja (Elipse)
            bubble_rect = [bx, by, bx + bubble_w, by + bubble_h]
            draw.ellipse(bubble_rect, fill="white", outline="black", width=2)
            
            # Dibujar texto
            draw.text((bx + padding, by + padding), wrapped_text, fill="black", font=font)

            # Nombre del personaje (opcional)
            if char:
                 draw.text((bx + padding, by - 5), char.upper(), fill="purple", font=small_font)

    def apply_final_overlays(self, base_image_path, panels):
        """Toma la imagen generada por IA y aplica los globos nítidos encima"""
        img = Image.open(base_image_path).convert("RGB")
        
        for panel in panels:
            layout = panel.get('layout')
            if not layout: continue
            
            x = int((layout['x'] / 100) * self.page_width)
            y = int((layout['y'] / 100) * self.page_height)
            w = int((layout['w'] / 100) * self.page_width)
            h = int((layout['h'] / 100) * self.page_height)
            
            self.draw_panel_balloons(img, panel, (x, y, w, h))
            
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
        img.save(tmp_file.name)
        return tmp_file.name
