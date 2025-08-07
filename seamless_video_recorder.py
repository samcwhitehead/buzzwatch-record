#!/usr/bin/env python3
"""
Seamless continuous video recorder using rpicam-vid
Records with no gaps between chunks and manages file storage

Error message:

2025-08-07 15:30:34,002 - INFO - Starting seamless video recording with rpicam-vid
2025-08-07 15:30:34,002 - INFO - Command: rpicam-vid -t 0 --segment 60000 -o /home/samwhitehead/Videos/video_20250807_153033_%04d.h264 --width 1920 --height 1080 --bitrate 10000000 --framerate 30 --codec h264 --inline --flush
2025-08-07 15:30:35,988 - INFO - Camera preview started
2025-08-07 15:30:35,988 - INFO - Seamless recording started - no gaps between chunks!
2025-08-07 15:30:35,989 - ERROR - Recording process ended unexpectedly:
2025-08-07 15:30:35,989 - ERROR - stdout: 
2025-08-07 15:30:35,990 - ERROR - stderr: [0:51:01.657819812] [2130]  INFO Camera camera_manager.cpp:326 libcamera v0.5.1+100-e53bdf1f
[0:51:01.674418471] [2138]  WARN CameraSensorProperties camera_sensor_properties.cpp:473 No static properties available for 'imx708_noir'
[0:51:01.674458675] [2138]  WARN CameraSensorProperties camera_sensor_properties.cpp:475 Please consider updating the camera sensor properties database
[0:51:01.687215906] [2138]  WARN RPiSdn sdn.cpp:40 Using legacy SDN tuning - please consider moving SDN inside rpi.denoise
[0:51:01.689082704] [2138]  WARN CameraSensor camera_sensor_legacy.cpp:501 'imx708_noir': No sensor delays found in static properties. Assuming unverified defaults.
[0:51:01.689878315] [2138]  INFO RPI vc4.cpp:440 Registered camera /base/soc/i2c0mux/i2c@1/imx708@1a to Unicam device /dev/media1 and ISP device /dev/media2
[0:51:01.689931352] [2138]  INFO RPI pipeline_base.cpp:1107 Using configuration file '/usr/share/libcamera/pipeline/rpi/vc4/rpi_apps.yaml'
Made X/EGL preview window
[0:51:02.453081525] [2130]  INFO Camera camera.cpp:1011 Pipeline handler in use by another process
ERROR: *** failed to acquire camera /base/soc/i2c0mux/i2c@1/imx708@1a ***

2025-08-07 15:30:35,990 - INFO - Stopping seamless video recording
2025-08-07 15:30:35,992 - INFO - Preview stopped
2025-08-07 15:30:35,992 - ERROR - Error stopping recording process: [Errno 3] No such process
2025-08-07 15:30:35,993 - INFO - No video files ready for transfer
2025-08-07 15:30:35,993 - INFO - Seamless recording stopped

"""

import os
import time
import shutil
import logging
import threading
import argparse
import subprocess
import signal
import glob
from datetime import datetime, timedelta
from pathlib import Path


class SeamlessVideoRecorder:
    def __init__(self,
                 local_storage_path="/home/samwhitehead/Videos",
                 external_storage_path="/media/samwhitehead/LaCie/buzzwatch_videos",
                 chunk_duration_minutes=20,
                 transfer_interval_hours=12.0,
                 show_preview=False,
                 resolution=(1920, 1080),
                 bitrate=10000000,
                 framerate=30):
        """
        Initialize the seamless video recorder using rpicam-vid

        Args:
            local_storage_path: Path on SD card to store videos temporarily
            external_storage_path: Path on external drive for long-term storage
            chunk_duration_minutes: Duration of each video chunk in minutes
            transfer_interval_hours: Hours between file transfers to external storage
            show_preview: Whether to show camera preview on connected display
            resolution: Video resolution as (width, height) tuple
            bitrate: Video bitrate in bits per second
            framerate: Video framerate (fps)
        """
        self.local_storage_path = Path(local_storage_path)
        self.external_storage_path = Path(external_storage_path)
        self.chunk_duration_ms = chunk_duration_minutes * 60 * 1000  # Convert to milliseconds
        self.transfer_interval = transfer_interval_hours * 3600  # Convert to seconds
        self.show_preview = show_preview
        self.resolution = resolution
        self.bitrate = bitrate
        self.framerate = framerate

        # Create directories
        self.local_storage_path.mkdir(parents=True, exist_ok=True)
        self.external_storage_path.mkdir(parents=True, exist_ok=True)

        # Process control
        self.recording_process = None
        self.preview_process = None
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

    def start_preview(self):
        """Start camera preview in separate window"""
        if not self.show_preview:
            return

        try:
            preview_cmd = [
                'rpicam-hello',
                '-t', '0',  # Run indefinitely
                '--preview', '0,0,640,480',  # Preview window size and position
                '--nopreview'  # Just test camera, don't actually show preview yet
            ]

            # Test if camera works first
            test_process = subprocess.run([
                'rpicam-hello', '-t', '1000'  # 1 second test
            ], capture_output=True)

            if test_process.returncode != 0:
                self.logger.warning("Camera test failed, preview may not work")
                return

            # Start actual preview
            self.preview_process = subprocess.Popen([
                'rpicam-hello',
                '-t', '0',
                '--preview', '0,0,640,480'
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            self.logger.info("Camera preview started")

        except Exception as e:
            self.logger.warning(f"Could not start preview: {e}")

    def stop_preview(self):
        """Stop camera preview"""
        if self.preview_process:
            try:
                self.preview_process.terminate()
                self.preview_process.wait(timeout=5)
            except:
                try:
                    self.preview_process.kill()
                except:
                    pass
            finally:
                self.preview_process = None
                self.logger.info("Preview stopped")

    def start_recording(self):
        """Start seamless video recording using rpicam-vid"""
        self.recording = True

        # Generate output filename pattern with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_pattern = str(self.local_storage_path / f"video_{timestamp}_%04d.h264")

        # Build rpicam-vid command
        record_cmd = [
            'rpicam-vid',
            '-t', '0',  # Record indefinitely
            '--segment', str(self.chunk_duration_ms),  # Segment duration in milliseconds
            '-o', output_pattern,  # Output file pattern
            '--width', str(self.resolution[0]),
            '--height', str(self.resolution[1]),
            '--bitrate', str(self.bitrate),
            '--framerate', str(self.framerate),
            '--codec', 'h264',
            '--inline',  # Inline headers for better compatibility
            '--flush'  # Flush each segment immediately
        ]

        # Add preview if not using separate preview window
        if not self.show_preview:
            record_cmd.extend(['--nopreview'])

        try:
            self.logger.info("Starting seamless video recording with rpicam-vid")
            self.logger.info(f"Command: {' '.join(record_cmd)}")

            # Start recording process
            self.recording_process = subprocess.Popen(
                record_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid  # Create new process group for clean termination
            )

            # Start file transfer thread
            self.transfer_thread = threading.Thread(target=self.transfer_worker, daemon=True)
            self.transfer_thread.start()

            # Start preview if requested
            if self.show_preview:
                self.start_preview()

            self.logger.info("Seamless recording started - no gaps between chunks!")

            # Monitor the recording process
            while self.recording:
                # Check if process is still running
                if self.recording_process.poll() is not None:
                    # Process ended unexpectedly
                    stdout, stderr = self.recording_process.communicate()
                    self.logger.error(f"Recording process ended unexpectedly:")
                    self.logger.error(f"stdout: {stdout.decode()}")
                    self.logger.error(f"stderr: {stderr.decode()}")
                    break

                # Check storage space
                self.check_storage_space()

                # Sleep for a bit before checking again
                time.sleep(30)

        except Exception as e:
            self.logger.error(f"Failed to start recording: {e}")
        finally:
            self.stop_recording()

    def stop_recording(self):
        """Stop recording and cleanup"""
        self.logger.info("Stopping seamless video recording")
        self.recording = False

        # Stop preview
        self.stop_preview()

        # Stop recording process
        if self.recording_process:
            try:
                # Send SIGTERM to the process group
                os.killpg(os.getpgid(self.recording_process.pid), signal.SIGTERM)

                # Wait for clean shutdown
                try:
                    self.recording_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    # Force kill if it doesn't stop gracefully
                    os.killpg(os.getpgid(self.recording_process.pid), signal.SIGKILL)

                self.logger.info("Recording process stopped")

            except Exception as e:
                self.logger.error(f"Error stopping recording process: {e}")
            finally:
                self.recording_process = None

        # Final file transfer
        self.transfer_files()
        self.logger.info("Seamless recording stopped")

    def get_video_files(self):
        """Get list of completed video files"""
        return list(self.local_storage_path.glob("*.h264"))

    def transfer_files(self):
        """Transfer video files from local to external storage"""
        try:
            if not self.external_storage_path.exists():
                self.logger.warning("External storage not accessible")
                return

            video_files = self.get_video_files()

            # Don't transfer the most recent file if recording is active (it might still be writing)
            if self.recording and video_files:
                # Sort by modification time and exclude the most recent
                video_files.sort(key=lambda f: f.stat().st_mtime)
                video_files = video_files[:-1]  # Exclude most recent file

            if not video_files:
                self.logger.info("No video files ready for transfer")
                return

            self.logger.info(f"Transferring {len(video_files)} video files")

            transferred_count = 0
            total_size = 0

            for video_file in video_files:
                try:
                    destination = self.external_storage_path / video_file.name

                    # Copy file
                    shutil.copy2(video_file, destination)

                    # Verify transfer
                    if destination.exists() and destination.stat().st_size == video_file.stat().st_size:
                        total_size += video_file.stat().st_size
                        video_file.unlink()  # Remove original
                        transferred_count += 1
                        self.logger.info(f"Transferred: {video_file.name}")
                    else:
                        self.logger.error(f"Transfer verification failed: {video_file.name}")

                except Exception as e:
                    self.logger.error(f"Failed to transfer {video_file.name}: {e}")

            self.logger.info(
                f"Transfer complete: {transferred_count} files, {total_size / (1024 * 1024 * 1024):.2f} GB")
            self.last_transfer_time = time.time()

        except Exception as e:
            self.logger.error(f"Error during file transfer: {e}")

    def transfer_worker(self):
        """Background worker for periodic file transfers"""
        while self.recording:
            current_time = time.time()
            if current_time - self.last_transfer_time >= self.transfer_interval:
                self.transfer_files()

            # Check every minute
            time.sleep(60)

    def check_storage_space(self):
        """Monitor storage space"""
        try:
            # Check local storage
            local_usage = shutil.disk_usage(self.local_storage_path)
            local_free_gb = local_usage.free / (1024 ** 3)

            if local_free_gb < 2.0:
                self.logger.warning(f"Low local storage: {local_free_gb:.1f} GB free")

            # Check external storage
            if self.external_storage_path.exists():
                external_usage = shutil.disk_usage(self.external_storage_path)
                external_free_gb = external_usage.free / (1024 ** 3)

                if external_free_gb < 5.0:
                    self.logger.warning(f"Low external storage: {external_free_gb:.1f} GB free")

        except Exception as e:
            self.logger.error(f"Error checking storage: {e}")

    def cleanup_old_files(self, days_to_keep=30):
        """Remove old files from external storage"""
        try:
            if not self.external_storage_path.exists():
                return

            cutoff_time = time.time() - (days_to_keep * 24 * 3600)
            old_files = []

            for video_file in self.external_storage_path.glob("*.h264"):
                if video_file.stat().st_mtime < cutoff_time:
                    old_files.append(video_file)

            if old_files:
                self.logger.info(f"Cleaning up {len(old_files)} old files")
                for old_file in old_files:
                    old_file.unlink()

        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")


def main():
    parser = argparse.ArgumentParser(description='Seamless video recorder using rpicam-vid')

    # Storage settings
    parser.add_argument('--local-path', default='/home/samwhitehead/Videos',
                        help='Local storage path (default: /home/samwhitehead/Videos)')
    parser.add_argument('--external-path', default='/media/samwhitehead/LaCie/buzzwatch_videos',
                        help='External storage path (default: /media/samwhitehead/LaCie/buzzwatch_videos)')

    # Recording settings
    parser.add_argument('--chunk-minutes', type=int, default=20,
                        help='Video chunk duration in minutes (default: 20)')
    parser.add_argument('--resolution', default='1920x1080',
                        help='Video resolution (default: 1920x1080)')
    parser.add_argument('--bitrate', type=int, default=10000000,
                        help='Video bitrate in bits per second (default: 10000000)')
    parser.add_argument('--framerate', type=int, default=30,
                        help='Video framerate (default: 30)')

    # Transfer settings
    parser.add_argument('--transfer-hours', type=float, default=12.0,
                        help='Hours between transfers - can be decimal (default: 12.0)')

    # Preview settings
    parser.add_argument('--preview', action='store_true',
                        help='Show camera preview in separate window')

    # Cleanup settings
    parser.add_argument('--cleanup-days', type=int, default=30,
                        help='Days to keep old files (default: 30)')

    args = parser.parse_args()

    # Parse resolution
    try:
        width, height = map(int, args.resolution.split('x'))
        resolution = (width, height)
    except ValueError:
        print(f"Invalid resolution: {args.resolution}")
        return 1

    # Create recorder
    recorder = SeamlessVideoRecorder(
        local_storage_path=args.local_path,
        external_storage_path=args.external_path,
        chunk_duration_minutes=args.chunk_minutes,
        transfer_interval_hours=args.transfer_hours,
        show_preview=args.preview,
        resolution=resolution,
        bitrate=args.bitrate,
        framerate=args.framerate
    )

    try:
        # Cleanup old files
        recorder.cleanup_old_files(args.cleanup_days)

        # Start recording
        recorder.start_recording()

    except KeyboardInterrupt:
        print("\nStopping recorder...")
        recorder.stop_recording()
    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
