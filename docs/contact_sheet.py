"""Combine the rendered slide previews into contact sheets for quick review."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DOCS = Path(__file__).resolve().parent
PREVIEW = DOCS / "preview"
COLUMNS = 3
ROWS = 5
THUMB_W = 620
GAP = 26
LABEL = 26
FONT = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 17)


def main() -> None:
    slides = sorted(PREVIEW.glob("slide-*.png"))
    per_sheet = COLUMNS * ROWS
    for sheet_index in range(0, len(slides), per_sheet):
        batch = slides[sheet_index : sheet_index + per_sheet]
        with Image.open(batch[0]) as sample:
            thumb_h = round(THUMB_W * sample.height / sample.width)
        width = COLUMNS * THUMB_W + (COLUMNS + 1) * GAP
        height = ROWS * (thumb_h + LABEL) + (ROWS + 1) * GAP
        sheet = Image.new("RGB", (width, height), (243, 246, 250))
        draw = ImageDraw.Draw(sheet)
        for index, path in enumerate(batch):
            row, col = divmod(index, COLUMNS)
            x = GAP + col * (THUMB_W + GAP)
            y = GAP + row * (thumb_h + LABEL + GAP)
            with Image.open(path) as image:
                sheet.paste(image.resize((THUMB_W, thumb_h)), (x, y))
            draw.rectangle([x, y, x + THUMB_W, y + thumb_h], outline=(206, 216, 230))
            draw.text((x + 2, y + thumb_h + 5), path.stem.replace("slide-", "Slide "), font=FONT, fill=(90, 105, 128))
        target = DOCS / f"deck-overview-{sheet_index // per_sheet + 1}.png"
        sheet.save(target)
        print(target)


if __name__ == "__main__":
    main()
