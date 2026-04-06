# --------------------------------------------------------------------
# Quick and dirty script that converts video files from .H264
# files to .MP4 by executing a command line ffmpeg call
#
# *NOTE:* if you want to change to general conversion, may not be 
# able to use ffmpeg copy, so would need to adjust 'convert_file'
# --------------------------------------------------------------------
########## IMPORTS #############
import os
import sys
import subprocess
from pathlib import Path


########## PARAMS #############
VIDEO_FOLDER = None  # full path to folder with .h264 files. if None, look for command line input

OLD_EXT = '.h264'  # parameterizing file extensions in case we want to generalize
NEW_EXT = '.mp4'   


########## FUNCTIONS #############
# --------------------------------------------------------------------------------------------
def convert_file(video_filename, out_folder=VIDEO_FOLDER, new_ext=NEW_EXT):
    """
    Conveneince function to convert a single video file from h264 to mp4
    
    Args:
        video_filename: string, full path to .H264 file to be converted
        out_folder: string, full path to folder where the .MP4 files should be saved
        new_ext: extension we want to convert files to. Should be '.mp4'
    Returns:
        result: a CompletedProcess object from subprocess 
        
    """
    import subprocess
    # just put the converted file into the same folder if we don't have an input
    if out_folder is None:
        out_folder = str(Path(video_filename).parent)
    
    # get full filename/path for output
    out_filename = (Path(out_folder) / Path(video_filename).stem).with_suffix(new_ext)
    
    # do conversion with ffmpeg
    result = subprocess.run(f"ffmpeg -i {video_filename} -c copy {out_filename}")
    if result.returncode != 0:
        print("Error:", result.stderr)
    else:
        print(f'Converted {video_filename} to {out_filename}')
        
    return result
    
# --------------------------------------------------------------------------------------------   
def convert_files_in_folder(video_folder=VIDEO_FOLDER, out_folder=VIDEO_FOLDER, 
                             old_ext=OLD_EXT, new_ext=NEW_EXT):
    """
    Function that does the h264-mp4 conversion for many files 
    
    Args:
        video_folder: string, full path to FOLDER where .H264 files are
        out_folder: string, full path to folder where the .MP4 files should be saved
        old_ext: extension of files we want to convert. Should be '.h264'
    Returns:
        result: a CompletedProcess object from subprocess 
    """
    # get list of files to convert
    h264_list = [fn for fn in os.listdir(video_folder) if fn.endswith(old_ext)]
    
    # loop through and convert
    for h264_fn in h264_list:
        # get full path to h264 file
        h264_filename_full = str(Path(video_folder) / h264_fn)
        
        # convert 
        _ = convert_file(h264_filename_full, out_folder=out_folder, new_ext=new_ext)
        
    return


########## MAIN #############
if __name__ == '__main__':
    # read in folder name from terminal input or as specified above
    if not VIDEO_FOLDER:
        video_folder_arg = sys.argv[1]
    else:
        video_folder_arg = VIDEO_FOLDER
    
    # also try to get output folder
    if len(sys.argv) > 2:
        out_folder_arg = sys.argv[2]
    else:
        out_folder_arg = video_folder_arg
    
    print(f'Converting all {OLD_EXT} files in {video_folder_arg} to {NEW_EXT} in {out_folder_arg}...')
    
    # run conversion
    convert_files_in_folder(video_folder=video_folder_arg, out_folder=out_folder_arg)
    
    # print when done
    print('...completed conversion')