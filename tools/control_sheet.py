import matplotlib.pyplot as plt
from barcode import Code128
from barcode.writer import ImageWriter
import os

def create_simple_sheet():
    # The codes you need
    commands = {
        "NEXT BOX": "||BOX||",
        "PHOTO TAKEN": "||PH||",
        "DELETE LAST": "||DEL||",
        "END RACK": "||END||"
    }

    print("Generating barcodes...")

    # Create a simple figure
    fig, axes = plt.subplots(len(commands), 1, figsize=(8, 10))
    plt.subplots_adjust(hspace=0.6)

    for ax in axes:
        ax.axis('off')

    for i, (label, code_content) in enumerate(commands.items()):
        # 1. Generate the barcode image file directly
        filename = f"temp_{i}"
        # write() automatically adds .png, so we don't add it here
        with open(filename + ".png", "wb") as f:
            Code128(code_content, writer=ImageWriter()).write(f)
        
        # 2. Read it back
        img = plt.imread(filename + ".png")
        
        # 3. Show it
        axes[i].imshow(img)
        axes[i].set_title(label, fontsize=20, weight='bold', pad=15)
        
        # 4. Cleanup
        try:
            os.remove(filename + ".png")
        except:
            pass

    # Save the final sheet
    plt.savefig("studio_control_sheet.png", dpi=150, bbox_inches='tight')
    print("✅ Done! Open 'studio_control_sheet.png' in this folder.")

if __name__ == "__main__":
    create_simple_sheet()
