from fileinput import filename
from PIL import Image, ImageDraw, ImageFont
import os
import logging
from io import BytesIO
import requests
import uuid
import math, tempfile



# def generate_menu_grid_image(items, cols=2, output_path=None, return_image=False):
#     """
#     items: list of tuples (item_name, price, image_url)
#     cols: number of columns in the grid
#     output_path: optional override file path
#     return_image: if True, return the in-memory PIL Image instead of saving to disk
#     """
#     if not items:
#         return None

#     item_width, item_height = 400, 400
#     label_height = 60  # Increased label area to fit bigger text
#     rows = (len(items) + cols - 1) // cols
#     grid_width = item_width * cols
#     grid_height = item_height * rows

#     # Create blank canvas
#     grid_img = Image.new("RGB", (grid_width, grid_height), color="white")

#     font_path = "fonts/Montserrat-Medium.ttf"
#     if not os.path.exists(font_path):
#         font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
#     try:
#         name_font = ImageFont.truetype(font_path, size=30)  # Bigger name
#         price_font = ImageFont.truetype(font_path, size=32)  # Even bigger price
#     except:
#         name_font = price_font = ImageFont.load_default()

#     for idx, (name, price, image_url) in enumerate(items):
#         r, c = divmod(idx, cols)
#         try:
#             response = requests.get(image_url)
#             img = Image.open(BytesIO(response.content)).convert("RGB")
#             img = img.resize((item_width, item_height - label_height))

#             # Create a new image with space for the label
#             combined = Image.new("RGB", (item_width, item_height), "white")
#             combined.paste(img, (0, 0))

#             # Draw text
#             draw = ImageDraw.Draw(combined)
#             label_y = item_height - label_height + 10
#             label_text = f"{name}   ${price:.2f}"


#             # draw.text((10, label_y), name, fill="black", font=name_font)
#             # name_width = draw.textlength(name, font=name_font)
#             # draw.text((10 + name_width + 20, label_y), f"${price:.2f}", fill="green", font=price_font)
#             draw.text((10, label_y), name, fill="black", font=name_font)
#             price_text = f"${price:.2f}"
#             price_y = label_y + name_font.size + 2  
#             draw.text((10, price_y), price_text, fill="green", font=price_font)

#             grid_img.paste(combined, (c * item_width, r * item_height))
#         except Exception as e:
#             logging.error(f"❌ Error loading image for {name}: {e}")

#     if return_image:
#         return grid_img

#     # Save to file
#     import tempfile
#     if output_path is None:
#         output_path = os.path.join(tempfile.gettempdir(), f"menu_grid_{uuid.uuid4().hex}.png")
    
#     grid_img.save(output_path)
#     logging.info(f"✅ Menu grid image saved to {output_path}")
#     return output_path


def generate_menu_grid_image(items, cols=2, max_items_per_grid=6, output_dir=None, return_images=False):
    """
    Creates one or more menu grid images, paginated by max_items_per_grid.
    items: list of tuples (item_name, price, image_url)
    cols: number of columns per grid
    max_items_per_grid: number of items per page
    output_dir: where to save images (if not returning in-memory)
    return_images: if True, return list of PIL Images instead of saving to disk
    Returns: list of image file paths or PIL Images
    """

    if not items:
        return []

    item_width, item_height = 400, 400
    label_height = 80
    output_dir = output_dir or tempfile.gettempdir()
    pages = math.ceil(len(items) / max_items_per_grid)

    font_path = "fonts/Montserrat-Medium.ttf"
    if not os.path.exists(font_path):
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    try:
        name_font = ImageFont.truetype(font_path, size=30)
        price_font = ImageFont.truetype(font_path, size=32)
    except:
        name_font = price_font = ImageFont.load_default()

    result = []

    for page in range(pages):
        chunk = items[page * max_items_per_grid : (page + 1) * max_items_per_grid]
        rows = (len(chunk) + cols - 1) // cols
        grid_width = item_width * cols
        grid_height = item_height * rows
        grid_img = Image.new("RGB", (grid_width, grid_height), color="white")

        for idx, (name, price, image_url) in enumerate(chunk):
            r, c = divmod(idx, cols)
            try:
                response = requests.get(image_url)
                img = Image.open(BytesIO(response.content)).convert("RGB")
                img = img.resize((item_width, item_height - label_height))
                combined = Image.new("RGB", (item_width, item_height), "white")
                combined.paste(img, (0, 0))

                draw = ImageDraw.Draw(combined)
                label_y = item_height - label_height + 10
                draw.text((10, label_y), name, fill="black", font=name_font)
                price_text = f"${price:.2f}"
                price_y = label_y + name_font.size + 2
                draw.text((10, price_y), price_text, fill="green", font=price_font)

                grid_img.paste(combined, (c * item_width, r * item_height))
            except Exception as e:
                logging.error(f"❌ Error loading image for {name}: {e}")

        if return_images:
            result.append(grid_img)
        else:
            filename = f"menu_grid_page_{page+1}_{uuid.uuid4().hex}.png"
            output_path = os.path.join(output_dir, filename)
            grid_img.save(output_path)
            logging.info(f"✅ Grid page {page+1} saved to {output_path}")
            result.append(output_path)

    return result

#GRID FOR BUTTONS
# def generate_menu_grid_image(items, page_number=1, per_page=4, cols=2, output_dir=None):
#     if not items:
#         return None, 0

#     total_pages = math.ceil(len(items) / per_page)
#     if page_number > total_pages or page_number < 1:
#         return None, total_pages

#     item_width, item_height, label_height = 400, 400, 60
#     page_items = items[(page_number - 1) * per_page : page_number * per_page]
#     rows = (len(page_items) + cols - 1) // cols
#     grid_width, grid_height = item_width * cols, item_height * rows
#     grid_img = Image.new("RGB", (grid_width, grid_height), color="white")

#     # Fonts
#     font_path = "fonts/Montserrat-Black.ttf"
#     if not os.path.exists(font_path):
#         font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
#     try:
#         name_font = ImageFont.truetype(font_path, size=40)
#         price_font = ImageFont.truetype(font_path, size=48)
#     except:
#         name_font = price_font = ImageFont.load_default()

#     for idx, (name, price, image_url) in enumerate(page_items):
#         r, c = divmod(idx, cols)
#         try:
#             response = requests.get(image_url)
#             img = Image.open(BytesIO(response.content)).convert("RGB")
#             img = img.resize((item_width, item_height - label_height))

#             combined = Image.new("RGB", (item_width, item_height), "white")
#             combined.paste(img, (0, 0))

#             draw = ImageDraw.Draw(combined)
#             label_y = item_height - label_height + 10
#             draw.text((10, label_y), name, fill="black", font=name_font)
#             name_width = draw.textlength(name, font=name_font)
#             draw.text((10 + name_width + 20, label_y), f"${price:.2f}", fill="green", font=price_font)

#             grid_img.paste(combined, (c * item_width, r * item_height))
#         except Exception as e:
#             print(f"Error loading image for {name}: {e}")

#     if output_dir is None:
#         output_dir = tempfile.gettempdir()
#     filename = f"menu_grid_page_{page_number}_{uuid.uuid4().hex}.png"
#     output_path = os.path.join(output_dir, filename)
#     grid_img.save(output_path)
#     return output_path, total_pages



# def generate_menu_grid_image(items, page_number=1, per_page=4, cols=2, output_dir=None):
#     if not items:
#         return None, 0
    
#     total_pages = math.ceil(len(items) / per_page)
#     if page_number > total_pages or page_number < 1:
#         return None, total_pages
    
#     item_width, item_height, label_height = 400, 400, 60
#     page_items = items[(page_number - 1) * per_page : page_number * per_page]
#     rows = (len(page_items) + cols - 1) // cols
#     grid_width, grid_height = item_width * cols, item_height * rows
#     grid_img = Image.new("RGB", (grid_width, grid_height), color="white")
    
#     # Fonts
#     font_path = "fonts/Montserrat-Black.ttf"
#     if not os.path.exists(font_path):
#         font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
#     try:
#         name_font = ImageFont.truetype(font_path, size=40)
#         price_font = ImageFont.truetype(font_path, size=48)
#     except:
#         name_font = price_font = ImageFont.load_default()
    
#     for idx, (name, price, image_url) in enumerate(page_items):
#         r, c = divmod(idx, cols)
#         try:
#             response = requests.get(image_url, timeout=10)
#             img = Image.open(BytesIO(response.content)).convert("RGB")
#             img = img.resize((item_width, item_height - label_height))
            
#             combined = Image.new("RGB", (item_width, item_height), "white")
#             combined.paste(img, (0, 0))
            
#             draw = ImageDraw.Draw(combined)
#             label_y = item_height - label_height + 10
#             draw.text((10, label_y), name, fill="black", font=name_font)
#             name_width = draw.textlength(name, font=name_font)
#             draw.text((10 + name_width + 20, label_y), f"${price:.2f}", fill="green", font=price_font)
            
#             grid_img.paste(combined, (c * item_width, r * item_height))
#         except Exception as e:
#             print(f"Error loading image for {name}: {e}")
#             # Add placeholder for failed images
#             placeholder = Image.new("RGB", (item_width, item_height - label_height), "lightgray")
#             combined = Image.new("RGB", (item_width, item_height), "white")
#             combined.paste(placeholder, (0, 0))
            
#             draw = ImageDraw.Draw(combined)
#             label_y = item_height - label_height + 10
#             draw.text((10, label_y), name, fill="black", font=name_font)
#             name_width = draw.textlength(name, font=name_font)
#             draw.text((10 + name_width + 20, label_y), f"${price:.2f}", fill="green", font=price_font)
            
#             grid_img.paste(combined, (c * item_width, r * item_height))
    
#     if output_dir is None:
#         output_dir = tempfile.gettempdir()
#     filename = f"menu_grid_page_{page_number}_{uuid.uuid4().hex}.png"
#     output_path = os.path.join(output_dir, filename)
#     grid_img.save(output_path)
#     return output_path, total_pages
