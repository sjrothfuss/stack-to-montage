"A module to create 2D montages from xyzc images."

import os
import math
import re
from array import array
from ij import IJ, ImagePlus, ImageStack
from ij.plugin import MontageMaker, RGBStackMerge
from ij.gui import Overlay, Line, TextRoi
from java.awt import Color
from ij.gui import GenericDialog

# If desired, set default paths here.
INPUT_STACK_PATH = ""
OUTPUT_AND_TEMP_DIR_PATH = ""

# TODO:
# [x] - Add user input for input and output paths?
# [x] - Add scale bar to montage
# [x] - Preserve original image name for saving montage
# [ ] - Add control over order of channels in montage by ordering stack
# [ ] - Adjust `make_montage()` to only look for the number of pngs 
# saved (may be reduced by user-selected options)


def double_split_and_montage():
    """Toplevel function for creating montage from xycz stack."""
    input_stack_path, output_dir_path = get_file_paths()
    print("Reading input file...")
    imp = IJ.openImage(input_stack_path)
    width = imp.getWidth()
    height = imp.getHeight()
    n_slices = imp.getNSlices()
    n_channels = imp.getNChannels()
    pixel_width = imp.getCalibration().pixelWidth
    pixel_unit = imp.getCalibration().getUnit()

    slices_to_include, bool_save_final_montage = get_options(n_slices)

    double_split_and_save(
        imp,
        n_slices,
        n_channels,
        pixel_width,
        pixel_unit,
        slices_to_include,
        output_dir_path,
    )
    stack_imp = read_and_stack(output_dir_path, width, height)
    montage = make_montage(
        stack_imp=stack_imp,
        n_slices=len(slices_to_include),
        n_channels=n_channels,
    )
    montage.show()
    if bool_save_final_montage:
        input_file_name = os.path.splitext(os.path.basename(input_stack_path))[0]
        save_png(
            imp=montage,
            file_name=input_file_name + "_Montage",
            output_dir=output_dir_path,
        )
    print("Done!")


def get_file_paths():
    """Get paths from user.

    Useful docuemntation for dialog GUIs:
    https://imagej.net/ij/developer/api/ij/ij/gui/GenericDialog.html

    """

    paths_dialog = GenericDialog("Set input and output paths")
    paths_dialog.addFileField("Input file:", INPUT_STACK_PATH, 50)
    paths_dialog.addDirectoryField("Output directory:", OUTPUT_AND_TEMP_DIR_PATH, 50)
    paths_dialog.showDialog()
    if paths_dialog.wasCanceled():
        raise RuntimeError("User cancelled dialog")
    input_file = paths_dialog.getNextString()
    output_dir = paths_dialog.getNextString()
    if not os.path.exists(input_file):
        IJ.error("Input file does not exist.")
        raise RuntimeError("Invalid input file")
    if not os.path.exists(output_dir):
        IJ.error("Output directory does not exist.")
        raise RuntimeError("Invalid output directory")

    return input_file, output_dir


def get_options(n_slices):
    """Get user input for which options

    Which planes to include in montage and whether to save final montage.
    """

    options_dialog = GenericDialog("Choose montage options")
    options_dialog.addMessage("Input file contains " + str(n_slices) + " z slices.")
    options = ["All slices", "Only odd slices", "Custom (comma separated):"]
    options_dialog.addRadioButtonGroup(
        "Select slices to include in montage:",  # label
        options,  # items
        len(options),  # no of rows
        1,  # no of columns
        options[0],  # default item
    )
    options_dialog.addStringField(
        "            ",  # label
        "1,6,7,42",  # default text
    )
    options_dialog.addCheckbox("Save final montage", True)

    options_dialog.showDialog()
    if options_dialog.wasCanceled():
        raise RuntimeError("User cancelled options dialog")

    slices_to_include = options_dialog.getNextRadioButton()
    custom_slices = options_dialog.getNextString()
    slices_to_include = _format_slices_input(slices_to_include, custom_slices, n_slices)
    bool_save_final_montage = options_dialog.getNextBoolean()

    return slices_to_include, bool_save_final_montage


def _format_slices_input(slices_option_selection, custom_slices, n_slices):
    """Format user input for slices to include in montage from str to list."""

    if slices_option_selection == "All slices":
        return list(range(1, n_slices + 1))
    if slices_option_selection == "Only odd slices":
        return list(range(1, n_slices + 1, 2))
    if slices_option_selection == "Custom (comma separated):":
        if not re.match(r"^[\d, ]+$", custom_slices):
            IJ.error(
                """Invalid input: Custom slices field must only contain numbers, """
                """spaces, and commas. Try again."""
            )
            raise ValueError("Invalid input for slices to include")
        custom_slices = custom_slices.replace(" ", "")
        custom_slices = custom_slices.split(",")
        custom_slices = [int(s) for s in custom_slices if int(s) <= n_slices]
        if custom_slices == []:
            IJ.error(
                """Invalid input: Custom slices field must contain at least one """
                """valid number that is less than the number of slices. Try again."""
            )
            raise ValueError("Invalid input for slices to include")
        return custom_slices


def double_split_and_save(
    imp,
    n_slices,
    n_channels,
    pixel_width,
    pixel_unit,
    slices_to_include,
    output_dir,
):
    """Split stack by z and c and save as PNGs."""
    original_luts = imp.getLuts()
    if n_slices == 1:
        IJ.showMessage(
            "Warning",
            (
                "Image only has one z-slice. If this is unexpected, check Image > "
                "Properties in FIJI."
            ),
        )
    print("Processing " + str(n_slices) + " slices...")
    for z in range(1, n_slices + 1):
        if z not in slices_to_include:
            continue
        imp.setZ(z)
        channel_images = []

        print("Saving " + str(n_channels) + " channels from slice " + str(z) + "...")
        for c in range(1, n_channels + 1):
            imp.setC(c)

            channel_name = (
                "temp_Channel_" + str(c).zfill(2) + "_Slice_" + str(z).zfill(3)
            )
            channel_imp = ImagePlus(channel_name, imp.getProcessor().duplicate())
            channel_imp.setLut(original_luts[c - 1])
            save_png(imp=channel_imp, file_name=channel_name, output_dir=output_dir)

            channel_images.append(channel_imp)
        channel_array = array(ImagePlus, channel_images)
        overlay_imp = RGBStackMerge.mergeChannels(channel_array, False)
        if z == 1:
            overlay_imp = add_scale_bar(overlay_imp, pixel_width, pixel_unit)
        overlay_name = "temp_All_Channel_Overlay_Slice_" + str(z).zfill(3)
        save_png(imp=overlay_imp, file_name=overlay_name, output_dir=output_dir)


def read_and_stack(output_dir, width, height):
    """Read PNGs and create a new stack.

    Have to save and re-read files because for some reason I can't get imps to stay
    their proper colors when restacking if I don't save first.
    """
    png_file_names = [
        f
        for f in os.listdir(output_dir)
        if f.endswith(".png") and f.startswith("temp_")
    ]
    # Forward sort is used to put the overlay as the top row of the
    # montage. Reverse sort would put the overlay in the bottom row of
    # the montage which may be asthetically preferred in some cases.
    png_file_names.sort(reverse=False)
    print("Montaging " + str(len(png_file_names)) + " panels...")

    new_stack = ImageStack(width, height)
    for png_name in png_file_names:
        png_file_path = os.path.join(output_dir, png_name)
        png_imp = IJ.openImage(png_file_path)
        new_stack.addSlice(png_name, png_imp.getProcessor().convertToRGB())
        os.remove(png_file_path)  # clean-up temp files

    stack_imp = ImagePlus("Reconstructed Color Stack", new_stack)
    stack_imp.setDimensions(1, len(png_file_names), 1)
    return stack_imp


def make_montage(stack_imp, n_slices, n_channels):
    """Create montage from stack."""
    return MontageMaker().makeMontage2(
        stack_imp,  # imp
        n_slices,  # columns
        n_channels + 1,  # rows, +1 to include overlay
        0.85,  # scale
        1,  # first image
        n_slices * (n_channels + 1),  # last image, +1 to include overlay
        1,  # increment
        0,  # border width
        False,  # labels
    )


def add_scale_bar(
    imp,
    pixel_width,
    pixel_unit,
    show_length=True,
    line_width=0,
    font_size=0,
):
    """Add reasonably long scale bar to imp.

    Derrived from
    https://forum.image.sc/t/automatic-scale-bar-in-fiji-imagej/60774.
    """

    if pixel_unit == "pixels":
        print("Warning! Image not spatially calibrated, cannot add scale bar.")
        return imp

    if pixel_unit == "micron":
        pixel_unit = "µm"[1:]  # Omitting Â character added by FIJI

    imp_height = imp.getHeight()
    imp_width = imp.getWidth()
    if line_width == 0:
        line_width = imp_height // 50
    if font_size == 0:
        font_size = line_width * 4
    scale_bar_x = 2 * line_width
    scale_bar_y = imp_height - 2 * line_width
    scale_bar_len = calculate_scale_bar_length(pixel_width, imp_width)

    # Create overlay
    overlay = Overlay()
    scale_bar_roi = Line(
        scale_bar_x,
        scale_bar_y,
        scale_bar_x + scale_bar_len / pixel_width,
        scale_bar_y,
    )
    scale_bar_roi.setStrokeColor(Color.WHITE)
    scale_bar_roi.setLineWidth(line_width)
    overlay.add(scale_bar_roi)

    scale_bar_text = str(int(scale_bar_len)) + " " + pixel_unit
    text_roi = TextRoi(
        scale_bar_x,  # x position
        scale_bar_y - (line_width + font_size),  # y position
        scale_bar_text, # text
    )
    text_roi.setColor(Color.WHITE)
    text_roi.setFontSize(font_size)
    # This option allows for printing the scale bar length instead of
    # displaying it on the image in the future.
    if show_length:
        overlay.add(text_roi)
    else:
        print("Scale bar length: " + scale_bar_text)

    imp.setOverlay(overlay)
    return imp


def calculate_scale_bar_length(pixel_width, imp_width):
    """Calculate the scale bar length using a 1-2-5 series."""
    image_width = pixel_width * imp_width
    scale_bar_size = 0.1  # approximate size of the scale bar relative to image width
    scale_bar_len = 1  # initial scale bar length in measurement units
    while scale_bar_len < image_width * scale_bar_size:
        scale_bar_len = round(
            (scale_bar_len * 2.3)
            / (10 ** math.floor(math.log10(abs(scale_bar_len * 2.3))))
        ) * (10 ** math.floor(math.log10(abs(scale_bar_len * 2.3))))
    return scale_bar_len


def save_png(imp, file_name, output_dir):
    """Save imp as PNG."""
    output_path = os.path.join(output_dir, file_name + ".png")
    IJ.saveAs(imp, "PNG", output_path)


double_split_and_montage()
