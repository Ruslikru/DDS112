"""Render the repository-native 112 app mark to Windows icon sizes."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
root=Path(__file__).resolve().parents[1]
folder=root/'packaging/assets'
folder.mkdir(parents=True,exist_ok=True)
folder.joinpath('trainer.svg').write_text('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><rect x="8" y="8" width="240" height="240" rx="48" fill="#1883b1"/><text x="128" y="156" fill="white" text-anchor="middle" font-family="Segoe UI, sans-serif" font-size="104" font-weight="700">112</text><rect x="54" y="187" width="148" height="14" rx="7" fill="#ff8a4a"/></svg>''',encoding='utf-8')
image=Image.new('RGBA',(1024,1024))
draw=ImageDraw.Draw(image)
draw.rounded_rectangle((32,32,992,992),radius=192,fill='#1883b1')
font=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf',416)
draw.text((512,434),'112',font=font,anchor='mm',fill='white')
draw.rounded_rectangle((216,748,808,804),radius=28,fill='#ff8a4a')
image.resize((256,256),Image.Resampling.LANCZOS).save(folder/'trainer.png')
image.save(folder/'trainer.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
