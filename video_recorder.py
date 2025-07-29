#!/usr/bin/env python3
"""
Continuous video recorder for Raspberry Pi 4 with Pi Camera
Records 20-minute H.264 video chunks and manages file storage

# -----------------
Key Features:
# -----------------
Video Recording:

Records in H.264 format at 1080p with 10 Mbps bitrate
Automatically creates 20-minute video chunks
Uses the modern picamera2 library for better performance

File Management:

Stores videos temporarily on SD card, then transfers to external USB drive every 12 hours
Includes file verification to ensure successful transfers
Automatic cleanup of old files (configurable retention period)

Monitoring & Safety:

Comprehensive logging to both file and console
Storage space monitoring with warnings
Graceful error handling and recovery

Optional Preview:

Can display live camera preview on connected monitor
Easily enabled/disabled via command line flag

Setup Requirements:
bash# Install required packages
sudo apt update
sudo apt install python3-pip

# Install Python dependencies
pip3 install picamera2

# Create mount point for external drive (if needed)
sudo mkdir /mnt/external_hdd

# Mount your external USB drive (replace /dev/sda1 with your drive)
sudo mount /dev/sda1 /mnt/external_hdd

# Make the script executable
chmod +x video_recorder.py


Usage Examples:
bash# Basic usage (default settings)
python3 video_recorder.py

# With preview enabled
python3 video_recorder.py --preview

# Custom settings
python3 video_recorder.py --chunk-minutes 30 --transfer-hours 6 --preview

# Different storage paths
python3 video_recorder.py --local-path /tmp/videos --external-path /media/usb/videos
Running as a Service:
To run this continuously, create a systemd service:
bash# Create service file
sudo nano /etc/systemd/system/video-recorder.service
Add this content:
ini[Unit]
Description=Continuous Video Recorder
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi
ExecStart=/usr/bin/python3 /home/pi/video_recorder.py --preview
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
Then enable and start the service:
bashsudo systemctl enable video-recorder.service
sudo systemctl start video-recorder.service
The script includes robust error handling, logging, and storage management to ensure reliable continuous operation on your Raspberry Pi.

"""

import os
import time
import shutil
import logging
import threading
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from picamera2 import Picamera2, Preview
from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput

class VideoRecorder:
    def __init__(self, local_storage_path="/home/samwhitehead/Videos", 
                 external_storage_path="/media/samwhitehead/LaCie/buzzwatch_videos",
                 chunk_duration_minutes=20, 
                 transfer_interval_hours=12,
                 show_preview=False,
                 resolution=(1920, 1080),
                 bitrate=10000000,
                 framerate=30,
                 preview_size=(640, 480)):
        """
        Initialize the video recorder
        
        Args:
            local_storage_path: Path on SD card to store videos temporarily
            external_storage_path: Path on external drive for long-term storage
            chunk_duration_minutes: Duration of each video chunk in minutes
            transfer_interval_hours: Hours between file transfers to external storage
            show_preview: Whether to show camera preview on connected display
            resolution: Video resolution as (width, height) tuple
            bitrate: Video bitrate in bits per second
            framerate: Video framerate (fps)
            preview_size: Preview window size as (width, height) tuple
        """
        self.local_storage_path = Path(local_storage_path)
        self.external_storage_path = Path(external_storage_path)
        self.chunk_duration = chunk_duration_minutes * 60  # Convert to seconds
        self.transfer_interval = transfer_interval_hours * 3600  # Convert to seconds
        self.show_preview = show_preview
        self.resolution = resolution
        self.bitrate = bitrate
        self.framerate = framerate
        self.preview_size = preview_size

        # Create directories if they don't exist
        self.local_storage_path.mkdir(parents=True, exist_ok=True)
        self.external_storage_path.mkdir(parents=True, exist_ok=True)
        
        # Preview process control
        self.preview_started = False
        
        # Initialize camera
        self.camera = Picamera2()
        self.encoder = H264Encoder(bitrate=self.bitrate)  # Use configurable bitrate
        
        # Threading control
        self.recording = False
        self.transfer_thread = None
        self.last_transfer_time = time.time()
        
        # Setup logging
        self.log_path = self.local_storage_path / Path('video_recorder.log')
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_path),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def stop_preview(self):
        """Stop camera preview """
        if self.preview_started:
            try:
                self.camera.stop_preview()
                self.preview_started = False
                self.logger.info("Camera preview stopped")
            except Exception as e:
                self.logger.warning(f"Error stopping preview: {e}")
                
    def setup_camera(self):
        """Configure camera settings for optimal recording"""
        try:
            # Start preview first if requested
            if self.show_preview:
                try:
                    self.camera.start_preview(Preview.QTGL)
                    self.preview_started = True
                    self.logger.info("QTGL camera preview started")
                except Exception as preview_error:
                    self.logger.warning(f"QTGL preview failed: {preview_error}")
                    try:
                        # Fallback to Qt preview
                        self.camera.start_preview(Preview.QT)
                        self.preview_started = True
                        self.logger.info("Qt camera preview started")
                    except Exception as qt_error:
                        self.logger.warning(f"Qt preview also failed: {qt_error}")
                        self.logger.warning("Continuing without preview")
                        
            # Configure camera for video recording
            if self.show_preview and self.preview_started:
                # if preview is running, use preview configuration initially
                preview_config = self.camera.create_preview_configuration()
                self.camera.configure(preview_config)
                self.camera.start()
                
                # Wait a moment for preview to stabilize
                time.sleep(2)
                self.camera.stop()
                
            # Now switch to video configuration for recording
            video_config = self.camera.create_video_configuration(
                main={"size": self.resolution, "format": "YUV420"},  # Use configurable resolution
            )
            self.camera.configure(video_config)
            self.camera.start()
        
            self.logger.info("Camera initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to setup camera: {e}")
            raise
    
    def generate_filename(self):
        """Generate timestamped filename for video chunks"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"video_chunk_{timestamp}.h264"
    
    def record_chunk(self):
        """Record a single video chunk"""
        filename = self.generate_filename()
        filepath = self.local_storage_path / filename
        
        try:
            self.logger.info(f"Starting recording: {filename}")
            
            # Create file output
            output = FileOutput(str(filepath))
            
            # Start recording
            self.camera.start_recording(self.encoder, output)
            
            # Record for specified duration
            time.sleep(self.chunk_duration)
            
            # Stop recording
            self.camera.stop_recording()
            
            self.logger.info(f"Completed recording: {filename} ({filepath.stat().st_size / (1024*1024):.1f} MB)")
            
        except Exception as e:
            self.logger.error(f"Error during recording: {e}")
            # Clean up partial file if it exists
            if filepath.exists():
                filepath.unlink()
    
    def transfer_files(self):
        """Transfer video files from local to external storage"""
        try:
            if not self.external_storage_path.exists():
                self.logger.warning("External storage path not accessible, skipping transfer")
                return
            
            video_files = list(self.local_storage_path.glob("*.h264"))
            
            if not video_files:
                self.logger.info("No video files to transfer")
                return
            
            self.logger.info(f"Transferring {len(video_files)} video files to external storage")
            
            transferred_count = 0
            total_size = 0
            
            for video_file in video_files:
                try:
                    destination = self.external_storage_path / video_file.name
                    
                    # Copy file to external storage
                    shutil.copy2(video_file, destination)
                    
                    # Verify transfer was successful
                    if destination.exists() and destination.stat().st_size == video_file.stat().st_size:
                        # Remove original file from local storage
                        total_size += video_file.stat().st_size
                        video_file.unlink()
                        transferred_count += 1
                        self.logger.info(f"Transferred: {video_file.name}")
                    else:
                        self.logger.error(f"Transfer verification failed for: {video_file.name}")
                        
                except Exception as e:
                    self.logger.error(f"Failed to transfer {video_file.name}: {e}")
            
            self.logger.info(f"Transfer complete: {transferred_count} files, {total_size / (1024*1024*1024):.2f} GB")
            self.last_transfer_time = time.time()
            
        except Exception as e:
            self.logger.error(f"Error during file transfer: {e}")
    
    def cleanup_old_files(self, days_to_keep=30):
        """Remove old video files from external storage (optional maintenance)"""
        try:
            if not self.external_storage_path.exists():
                return
            
            cutoff_time = time.time() - (days_to_keep * 24 * 3600)
            old_files = []
            
            for video_file in self.external_storage_path.glob("*.h264"):
                if video_file.stat().st_mtime < cutoff_time:
                    old_files.append(video_file)
            
            if old_files:
                self.logger.info(f"Cleaning up {len(old_files)} old video files")
                for old_file in old_files:
                    old_file.unlink()
                    self.logger.info(f"Deleted old file: {old_file.name}")
        
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
    
    def check_storage_space(self):
        """Monitor storage space and log warnings if running low"""
        try:
            # Check local storage (SD card)
            local_usage = shutil.disk_usage(self.local_storage_path)
            local_free_gb = local_usage.free / (1024**3)
            
            if local_free_gb < 2.0:  # Less than 2GB free
                self.logger.warning(f"Low local storage space: {local_free_gb:.1f} GB free")
            
            # Check external storage
            if self.external_storage_path.exists():
                external_usage = shutil.disk_usage(self.external_storage_path)
                external_free_gb = external_usage.free / (1024**3)
                
                if external_free_gb < 5.0:  # Less than 5GB free
                    self.logger.warning(f"Low external storage space: {external_free_gb:.1f} GB free")
        
        except Exception as e:
            self.logger.error(f"Error checking storage space: {e}")
    
    def start_recording(self):
        """Start continuous video recording"""
        self.recording = True
        self.logger.info("Starting continuous video recording")
        
        try:
            self.setup_camera()
            
            # Start background transfer thread
            self.transfer_thread = threading.Thread(target=self.transfer_worker, daemon=True)
            self.transfer_thread.start()
            
            while self.recording:
                # Record a chunk
                self.record_chunk()
                
                # Check storage space periodically
                self.check_storage_space()
                
                # Small pause between chunks to prevent issues
                if self.recording:
                    time.sleep(1)
        
        except KeyboardInterrupt:
            self.logger.info("Recording interrupted by user")
        except Exception as e:
            self.logger.error(f"Recording error: {e}")
        finally:
            self.stop_recording()
    
    def transfer_worker(self):
        """Background worker for periodic file transfers"""
        while self.recording:
            current_time = time.time()
            if current_time - self.last_transfer_time >= self.transfer_interval:
                self.transfer_files()
            
            # Check every minute
            time.sleep(60)
    
    def stop_recording(self):
        """Stop recording and cleanup"""
        self.logger.info("Stopping video recording")
        self.recording = False
        
        # Stop preview first
        self.stop_preview()
        
        try:
            if hasattr(self.camera, 'stop_recording'):
                self.camera.stop_recording()
            self.camera.stop()
            self.camera.close()
        except Exception as e:
            self.logger.error(f"Error stopping camera: {e}")
        
        # Perform final file transfer
        self.transfer_files()
        
        self.logger.info("Video recording stopped")

def main():
    parser = argparse.ArgumentParser(description='Continuous video recorder for Raspberry Pi')

    # Storage settings
    parser.add_argument('--local-path', default='/home/samwhitehead/Videos',
                      help='Local storage path (default: /home/samwhitehead/Videos)')
    parser.add_argument('--external-path', default='/media/samwhitehead/LaCie/buzzwatch_videos',
                      help='External storage path (default: /media/samwhitehead/LaCie/buzzwatch_videos)')

    # Recording settings
    parser.add_argument('--chunk-minutes', type=int, default=1,
                        help='Video chunk duration in minutes (default: 20)')
    parser.add_argument('--resolution', default='1920x1080',
                        help='Video resolution (default: 1920x1080). Options: 1920x1080, 1280x720, 640x480')
    parser.add_argument('--bitrate', type=int, default=10000000,
                        help='Video bitrate in bits per second (default: 10000000 = 10Mbps)')
    parser.add_argument('--framerate', type=int, default=30,
                        help='Video framerate (default: 30)')

    # Transfer and cleanup settings
    parser.add_argument('--transfer-hours', type=float, default=0.05,
                        help='Hours between transfers (default: 12)')
    parser.add_argument('--cleanup-days', type=int, default=30,
                        help='Days to keep old files (default: 30)')

    # Display settings
    parser.add_argument('--preview', action='store_true',
                        help='Show camera preview on connected display')
    parser.add_argument('--preview-size', default='640x480',
                        help='Preview window size (default: 640x480)')

    args = parser.parse_args()

    # Parse resolution
    try:
        width, height = map(int, args.resolution.split('x'))
        resolution = (width, height)
    except ValueError:
        print(f"Invalid resolution format: {args.resolution}. Use format like 1920x1080")
        return 1

    # Parse preview size
    try:
        preview_width, preview_height = map(int, args.preview_size.split('x'))
        preview_size = (preview_width, preview_height)
    except ValueError:
        print(f"Invalid preview size format: {args.preview_size}. Use format like 640x480")
        return 1

    # Create recorder instance
    recorder = VideoRecorder(
        local_storage_path=args.local_path,
        external_storage_path=args.external_path,
        chunk_duration_minutes=args.chunk_minutes,
        transfer_interval_hours=args.transfer_hours,
        show_preview=args.preview,
        resolution=resolution,
        bitrate=args.bitrate,
        framerate=args.framerate,
        preview_size=preview_size
    )
    
    try:
        # Optionally cleanup old files on startup
        recorder.cleanup_old_files(args.cleanup_days)
        
        # Start recording
        recorder.start_recording()
        
    except Exception as e:
        print(f"Failed to start recorder: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
