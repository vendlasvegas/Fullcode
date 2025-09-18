#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SelfCheck.py
# Idle slideshow on HDMI + PriceCheck mode
# Target display: 1280x1024 (square format)
# Price Checker is Good
# Admin Login Screen Good / Secret button Top Left Passwords good long press
# Starting to test cart functions
# Manual Entry Added and working with image pull up
# Setting up Pay Now options, Venmo and Stripe good
# reciept working
# CashApp Working
# Inventory Synced to Inv tab
# Transactions synced
# Email Receipt 
# Working on Admin Functions
# Toggle input for payment methods and reciept printing
# Discount Logic working, need to still fix the spreadsheet logging for redemptions
# Security Camera integratin into cart mode
# 9/17/25 upload to git hub 16:00

import os
import random
import threading
import time
import subprocess
import logging
from pathlib import Path
from datetime import datetime
import io
import json
import shutil
import requests
import csv
import uuid
import http.server
import stripe
import re  # For regex in _format_receipt_for_sms
import cv2


import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk, ImageFont, ImageDraw
from tkinter import ttk
from googleapiclient.http import MediaFileUpload


import RPi.GPIO as GPIO

# Google Sheets & Drive
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


# ==============================
#           LOGGING
# ==============================
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')


# ==============================
#           CONFIG
# ==============================

# Window - Updated for 1280x1024 resolution
WINDOW_W, WINDOW_H = 1280, 1024

# Admin Mode
ADMIN_BG_PATH = Path.home() / "SelfCheck" / "SysPics" / "Admin.png"
CRED_DIR = Path.home() / "SelfCheck" / "Cred"
GS_CRED_TAB = "Credentials"  # Tab name for admin credentials
GS_LOGIN_TAB = "Login"       # Tab name for login credentials
ADMIN_TIMEOUT_MS = 90_000    # 90 seconds inactivity timeout

# Idle mode
IDLE_DIR = Path.home() / "SelfCheck" / "IdlePics"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}
SLIDE_MS = 20_000  # 20s

# Weather update interval
WEATHER_UPDATE_INTERVAL = 30 * 60  # 30 minutes in seconds

# GPIO Configuration
GPIO.setmode(GPIO.BCM)

# Button pins
PIN_RED    = 5   # Exit PriceCheck -> Idle
PIN_GREEN  = 6   # Enter PriceCheck / Reset scan
PIN_YELLOW = 12  # Available
PIN_BLUE   = 13  # Available
PIN_CLEAR  = 16  # Enter Admin mode

# Setup with pull-up resistors
GPIO.setup(PIN_RED,    GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(PIN_GREEN,  GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(PIN_YELLOW, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(PIN_BLUE,   GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(PIN_CLEAR,  GPIO.IN, pull_up_down=GPIO.PUD_UP)

# PriceCheck assets & layout
SYSPICS_DIR   = Path.home() / "SelfCheck" / "SysPics"
PRICE_BG_PATH = SYSPICS_DIR / "PriceCheck.png"

# Google Drive folder ID for product images
GDRIVE_FOLDER_ID = "1lbYM1WBgqvPwiRwvluJnVyKRawQgl5LU"

GS_CRED_PATH  = Path.home() / "SelfCheck" / "Cred" / "credentials.json"
GS_SHEET_NAME = "Inventory1001"
GS_TAB        = "Inv"

# Updated layout boxes for 1280x1024 resolution
# Scaled up from original 800x480 resolution
PC_BLUE_BOX  = (32, 357, 704, 777)     # Scaled from (20, 170, 440, 370)
PC_GREEN_BOX = (736, 462, 1248, 882)   # Scaled from (460, 220, 780, 420)

# Inactivity timeout
PRICECHECK_TIMEOUT_MS = 15_000  # 15s


# ==============================
#        FONT HELPERS
# ==============================

def load_ttf(size):
    for p in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

# Updated font sizes for 1280x1024 resolution
PC_FONT_TITLE = load_ttf(56)   # was 40
PC_FONT_SUB   = load_ttf(34)   # was 24
PC_FONT_INFO  = load_ttf(25)   # was 18
PC_FONT_LINE  = load_ttf(39)   # was 28
PC_FONT_SMALL = load_ttf(22)   # was 16


# ==============================
#        GENERIC HELPERS
# ==============================

def run(cmd):
    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, timeout=1.5)
        return out.decode("utf-8", "ignore").strip()
    except Exception:
        return ""

def get_wifi_rssi_dbm():
    txt = run("iw dev wlan0 link")
    for line in txt.splitlines():
        if "signal:" in line.lower():
            try:
                return int(float(line.split("signal:")[1].split("dBm")[0].strip()))
            except Exception:
                return None
    return None

def rssi_to_bars(rssi):
    if rssi is None: return 0
    if rssi >= -55: return 4
    if rssi >= -65: return 3
    if rssi >= -75: return 2
    if rssi >= -85: return 1
    return 0


# ==============================
#           IDLE MODE
# ==============================

class IdleMode:
    """Fullscreen slideshow with weather, time, and selection screen."""
    def __init__(self, root: tk.Tk):
        self.root = root
        # Main image display
        self.label = tk.Label(root, bg="black")
        
        # Create overlay labels - but don't place them yet
        # Bottom text
        self.bottom_text = tk.Label(root, text="Tap Anywhere to Start", 
                                   font=("Arial", 36, "bold"), fg="white", bg="black")
        
        # Top time display
        self.time_label = tk.Label(root, text="", font=("Arial", 24), fg="white", bg="black")
        
        # Weather display
        self.weather_label = tk.Label(root, text="", font=("Arial", 24), fg="white", bg="black")
        
        # Variables for long press detection
        self.press_start_time = 0
        self.long_press_timer = None
        self.long_press_duration = 2000  # 2 seconds for long press
        
        # Selection screen elements
        self.selection_active = False
        self.selection_label = tk.Label(root, bg="black")
        self.cart_button = tk.Label(root, bg="black")
        self.pc_button = tk.Label(root, bg="black")
        self.admin_button = tk.Label(root, bg="black")  # Logo button for admin access
        self.selection_timeout = None
        
        # Load button images
        self.cart_img = None
        self.pc_img = None
        self.logo_img = None
        self._load_button_images()
        
        # Add touch support to all elements
        self.label.bind("<Button-1>", self._on_touch)
        self.bottom_text.bind("<Button-1>", self._on_touch)
        self.time_label.bind("<Button-1>", self._on_touch)
        self.weather_label.bind("<Button-1>", self._on_touch)
        
        # Selection screen bindings
        self.selection_label.bind("<Button-1>", self._on_selection_background_click)
        self.cart_button.bind("<Button-1>", self._on_cart_button_click)
        self.pc_button.bind("<Button-1>", self._on_pc_button_click)
        
        self.tk_img = None
        self.slide_after = None
        self.overlay_timer = None
        self.order = []
        self.idx = 0
        self.is_active = False
        
        # Weather data
        self.weather_data = None
        self.weather_last_update = 0
        self.zipcode = None
        self.weather_api_key = None


    def _check_and_upload_videos(self):
        """Check for videos to upload after 10 minutes in idle mode."""
        if not self.is_active:
            return
            
        # Check if we've been in idle mode for at least 10 minutes
        current_time = time.time()
        if not hasattr(self, 'idle_start_time'):
            self.idle_start_time = current_time
            
        elapsed_minutes = (current_time - self.idle_start_time) / 60
        
        if elapsed_minutes >= 10:
            logging.info("Idle for 10+ minutes, checking for videos to upload")
            
            # Reset timer so we don't check again for another 10 minutes
            self.idle_start_time = current_time
            
            # Start upload in a separate thread
            threading.Thread(target=self._upload_videos_to_drive, daemon=True).start()
        
        # Check again in 60 seconds
        self.video_check_timer = self.root.after(60000, self._check_and_upload_videos)

    def _upload_videos_to_drive(self):
        """Upload videos to Google Drive and delete local copies."""
        videos_dir = Path.home() / "SelfCheck" / "TransactionVideos"
        if not videos_dir.exists():
            logging.info("No TransactionVideos directory found")
            return
            
        # Get list of video files
        video_files = list(videos_dir.glob("*.avi"))
        if not video_files:
            logging.info("No videos found to upload")
            return
            
        logging.info(f"Found {len(video_files)} videos to upload")
        
        # Initialize Google Drive API
        try:
            scopes = [
                "https://www.googleapis.com/auth/drive",
                "https://www.googleapis.com/auth/drive.file",
            ]
            creds = Credentials.from_service_account_file(str(GS_CRED_PATH), scopes=scopes)
            drive_service = build('drive', 'v3', credentials=creds)
            
            # Find or create TransactionVideos folder in Google Drive
            folder_id = self._find_or_create_drive_folder(drive_service, "TransactionVideos")
            if not folder_id:
                logging.error("Failed to find or create TransactionVideos folder in Google Drive")
                return
                
            # Upload each video
            for video_path in video_files:
                try:
                    logging.info(f"Uploading {video_path.name} to Google Drive")
                    self._upload_file_to_drive(drive_service, video_path, folder_id)
                    
                    # Delete local file after successful upload
                    video_path.unlink()
                    logging.info(f"Deleted local file: {video_path}")
                except Exception as e:
                    logging.error(f"Error uploading {video_path.name}: {e}")
        except Exception as e:
            logging.error(f"Error initializing Google Drive API: {e}")

    def _find_or_create_drive_folder(self, drive_service, folder_name):
        """Find or create a folder in Google Drive."""
        try:
            # Check if folder exists
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            results = drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
            items = results.get('files', [])
            
            if items:
                # Folder exists, return its ID
                return items[0]['id']
            else:
                # Create folder
                file_metadata = {
                    'name': folder_name,
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                folder = drive_service.files().create(body=file_metadata, fields='id').execute()
                return folder.get('id')
        except Exception as e:
            logging.error(f"Error finding/creating Drive folder: {e}")
            return None

    def _upload_file_to_drive(self, drive_service, file_path, folder_id):
        """Upload a file to Google Drive folder."""
        try:
            file_metadata = {
                'name': file_path.name,
                'parents': [folder_id]
            }
            
            media = MediaFileUpload(
                str(file_path),
                mimetype='video/x-msvideo',
                resumable=True
            )
            
            file = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            logging.info(f"Uploaded {file_path.name} to Google Drive with ID: {file.get('id')}")
            return True
        except Exception as e:
            logging.error(f"Error uploading to Drive: {e}")
            return False
    
    


    def start_command_checker(self):
        """Start periodic checking for remote commands in Google Sheets."""
        logging.info("Starting remote command checker")
        self._check_remote_commands()
        
    def _check_remote_commands(self):
        """Check for remote commands in the Command tab of Google Sheets."""
        if not self.is_active:
            return
            
        try:
            # Connect to Google Sheet
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_file(str(GS_CRED_PATH), scopes=scopes)
            gc = gspread.authorize(creds)
            
            # Open the Command tab
            sheet = gc.open(GS_SHEET_NAME).worksheet("Command")
            
            # Check cell A1 for restart command
            command = sheet.acell('A1').value
            
            if command == "Restart":
                logging.info("Remote restart command detected")
                
                # Clear the command cell - FIXED THIS LINE
                sheet.update_cell(1, 1, "")  # Row 1, Column 1 is A1
                
                # Log to Service tab
                service_sheet = gc.open(GS_SHEET_NAME).worksheet("Service")
                timestamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
                service_sheet.append_row([timestamp, "Remote User", "System Remote Restart"])
                
                # Show restart popup with countdown
                self._show_restart_countdown()
                return
                
        except Exception as e:
            logging.error(f"Error checking remote commands: {e}")
        
        # Schedule next check in 90 seconds if still active
        if self.is_active:
            self.command_check_timer = self.root.after(90000, self._check_remote_commands)

        
    def _show_restart_countdown(self):
        """Show restart countdown popup."""
        # Create popup frame
        self.restart_popup = tk.Frame(self.root, bg="#2c3e50", bd=3, relief=tk.RAISED)
        self.restart_popup.place(relx=0.5, rely=0.5, width=500, height=300, anchor=tk.CENTER)
        
        # Title
        title_label = tk.Label(self.restart_popup, text="System Restarting:", 
                             font=("Arial", 24, "bold"), bg="#2c3e50", fg="white")
        title_label.pack(pady=(40, 20))
        
        # Countdown label
        self.restart_countdown_value = 15
        self.restart_countdown_label = tk.Label(self.restart_popup, 
                                              text=f"{self.restart_countdown_value}", 
                                              font=("Arial", 48, "bold"), bg="#2c3e50", fg="white")
        self.restart_countdown_label.pack(pady=20)
        
        # Start countdown
        self._update_restart_countdown()
        
    def _update_restart_countdown(self):
        """Update the restart countdown timer."""
        self.restart_countdown_value -= 1
        self.restart_countdown_label.config(text=f"{self.restart_countdown_value}")
        
        if self.restart_countdown_value <= 0:
            # Time to restart
            if hasattr(self, "on_remote_restart"):
                self.on_remote_restart()
            return
            
        self.restart_countdown_timer = self.root.after(1000, self._update_restart_countdown)


    def _load_button_images(self):
        """Load button images."""
        try:
            # Load cart button image
            cart_path = Path.home() / "SelfCheck" / "SysPics" / "CartButton.png"
            if cart_path.exists():
                with Image.open(cart_path) as img:
                    # Resize to 50% of original size
                    w, h = img.size
                    img = img.resize((w//2, h//2), Image.LANCZOS)
                    self.cart_img = ImageTk.PhotoImage(img)
            else:
                logging.error(f"Cart button image not found: {cart_path}")
                
            # Load price check button image
            pc_path = Path.home() / "SelfCheck" / "SysPics" / "PCButton.jpeg"
            if pc_path.exists():
                with Image.open(pc_path) as img:
                    # Resize to 50% of original size
                    w, h = img.size
                    img = img.resize((w//2, h//2), Image.LANCZOS)
                    self.pc_img = ImageTk.PhotoImage(img)
            else:
                logging.error(f"Price check button image not found: {pc_path}")
                
            # Load logo image for admin button
            logo_path = Path.home() / "SelfCheck" / "SysPics" / "AdminButton.png"
            if logo_path.exists():
                with Image.open(logo_path) as img:
                    # Resize to a reasonable size for the admin button
                    img = img.resize((100, 100), Image.LANCZOS)
                    self.logo_img = ImageTk.PhotoImage(img)
            else:
                logging.error(f"Logo image not found: {logo_path}")
                
        except Exception as e:
            logging.error(f"Error loading button images: {e}")
    
    def _show_selection_screen(self):
        """Show selection screen with cart and price check buttons."""
        # Cancel slide show
        if self.slide_after:
            self.root.after_cancel(self.slide_after)
            self.slide_after = None
            
        # Hide overlays
        self.bottom_text.place_forget()
        self.time_label.place_forget()
        self.weather_label.place_forget()
        
        # Load default background
        default_bg_path = Path.home() / "SelfCheck" / "SysPics" / "Default.png"
        if default_bg_path.exists():
            try:
                with Image.open(default_bg_path) as img:
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    bg = self._letterbox(img)
                    self.tk_img = ImageTk.PhotoImage(bg)
                    self.selection_label.configure(image=self.tk_img)
            except Exception as e:
                logging.error(f"Error loading default background: {e}")
                # Fallback to black background
                self.selection_label.configure(bg="black")
        else:
            logging.error(f"Default background image not found: {default_bg_path}")
            self.selection_label.configure(bg="black")
            
        # Place selection screen elements
        self.selection_label.place(x=0, y=0, width=WINDOW_W, height=WINDOW_H)
        
        # Place buttons if images loaded successfully
        if self.cart_img:
            self.cart_button.configure(image=self.cart_img)
            # Position at middle height, left side
            cart_w = self.cart_img.width()
            cart_h = self.cart_img.height()
            self.cart_button.place(x=WINDOW_W//4 - cart_w//2, y=WINDOW_H//2 - cart_h//2)
            
        if self.pc_img:
            self.pc_button.configure(image=self.pc_img)
            # Position at middle height, right side
            pc_w = self.pc_img.width()
            pc_h = self.pc_img.height()
            self.pc_button.place(x=3*WINDOW_W//4 - pc_w//2, y=WINDOW_H//2 - pc_h//2)
            
        # Place logo button in bottom right corner
        if self.logo_img:
            self.admin_button.configure(image=self.logo_img)
            logo_w = self.logo_img.width()
            logo_h = self.logo_img.height()
            self.admin_button.place(x=WINDOW_W - logo_w - 20, y=WINDOW_H - logo_h - 20)
            
            # Add long press detection
            self.admin_button.bind("<Button-1>", self._on_admin_button_press)
            self.admin_button.bind("<ButtonRelease-1>", self._on_admin_button_release)
        else:
            # Fallback if logo image not found
            self.admin_button.configure(text="Admin", bg="#3498db", fg="white", 
                                      font=("Arial", 12))
            self.admin_button.place(x=WINDOW_W - 80, y=WINDOW_H - 40, width=60, height=30)
            
            # Add long press detection
            self.admin_button.bind("<Button-1>", self._on_admin_button_press)
            self.admin_button.bind("<ButtonRelease-1>", self._on_admin_button_release)
            
        # Lift all elements
        self.selection_label.lift()
        self.cart_button.lift()
        self.pc_button.lift()
        self.admin_button.lift()
        
        self.selection_active = True
        
        # Set timeout to return to idle mode after 30 seconds
        self.selection_timeout = self.root.after(30000, self._hide_selection_screen)
    
    def _on_admin_button_press(self, event):
        """Start timer for long press detection."""
        if not self.is_active:
            return
            
        self.press_start_time = time.time()
        # Cancel any existing timer
        if self.long_press_timer:
            self.root.after_cancel(self.long_press_timer)
        
        # Start a new timer for long press detection
        self.long_press_timer = self.root.after(self.long_press_duration, self._check_long_press)
    
    def _on_admin_button_release(self, event):
        """Cancel long press detection on button release."""
        if self.long_press_timer:
            self.root.after_cancel(self.long_press_timer)
            self.long_press_timer = None
    
    def _check_long_press(self):
        """Check if button has been pressed long enough."""
        self.long_press_timer = None
        # If we got here, the button was held long enough
        logging.info("Admin button long-pressed, entering Admin mode")
        if hasattr(self, "on_wifi_tap"):
            self.on_wifi_tap()
            
        # Cancel selection screen timeout
        if self.selection_timeout:
            self.root.after_cancel(self.selection_timeout)
            self.selection_timeout = None


 

    def _update_overlays(self):
        """Update text overlays"""
        if not self.is_active:
            return
            
        # Position bottom text
        self.bottom_text.place(x=WINDOW_W//2, y=WINDOW_H-50, anchor="center")
        
        # Update and position time
        current_time = datetime.now().strftime("%I:%M %p")
        self.time_label.config(text=current_time)
        self.time_label.place(x=WINDOW_W-100, y=30, anchor="center")
        
        # Update and position weather
        if self.weather_data:
            try:
                temp = self.weather_data.get('main', {}).get('temp', 'N/A')
                city = self.weather_data.get('name', 'Unknown')
                # Use the word "degrees" instead of the symbol
                weather_text = f"{city} {int(temp)} degrees F"
                self.weather_label.config(text=weather_text)
                self.weather_label.place(x=WINDOW_W//2, y=30, anchor="center")
            except Exception as e:
                logging.error(f"Error displaying weather: {e}")
        
        # Ensure overlays stay on top
        self._lift_overlays()
        
        # Schedule next update only if still active
        if self.is_active:
            self.overlay_timer = self.root.after(1000, self._update_overlays)

        
    def _on_admin_button_press(self, event):
        """Start timer for long press detection."""
        if not self.is_active:
            return
            
        self.press_start_time = time.time()
        # Cancel any existing timer
        if self.long_press_timer:
            self.root.after_cancel(self.long_press_timer)
        
        # Start a new timer for long press detection
        self.long_press_timer = self.root.after(self.long_press_duration, self._check_long_press)
    
    def _on_admin_button_release(self, event):
        """Cancel long press detection on button release."""
        if self.long_press_timer:
            self.root.after_cancel(self.long_press_timer)
            self.long_press_timer = None
    
    def _check_long_press(self):
        """Check if button has been pressed long enough."""
        self.long_press_timer = None
        # If we got here, the button was held long enough
        logging.info("Admin button long-pressed, entering Admin mode")
        if hasattr(self, "on_wifi_tap"):
            self.on_wifi_tap()

    def _update_overlays(self):
        """Update text overlays"""
        if not self.is_active:
            return
            
        # Position bottom text
        self.bottom_text.place(x=WINDOW_W//2, y=WINDOW_H-50, anchor="center")
        
        # Update and position time
        current_time = datetime.now().strftime("%I:%M %p")
        self.time_label.config(text=current_time)
        self.time_label.place(x=WINDOW_W-100, y=30, anchor="center")
        
        # Update and position weather
        if self.weather_data:
            try:
                temp = self.weather_data.get('main', {}).get('temp', 'N/A')
                city = self.weather_data.get('name', 'Unknown')
                # Use the word "degrees" instead of the symbol
                weather_text = f"{city} {int(temp)} degrees F"
                self.weather_label.config(text=weather_text)
                self.weather_label.place(x=WINDOW_W//2, y=30, anchor="center")
            except Exception as e:
                logging.error(f"Error displaying weather: {e}")

        
        # Position hidden admin button in top-left corner - increased size by 50%
        # Original size was 25x25, increasing by 50% makes it 38x38
        self.admin_button.place(x=0, y=0, width=38, height=38)
        
        # Ensure overlays stay on top
        self._lift_overlays()
        
        # Schedule next update only if still active
        if self.is_active:
            self.overlay_timer = self.root.after(1000, self._update_overlays)        

    def _on_touch(self, event):
        """Touch handler for idle mode"""
        if not self.is_active:
            return
        
        x, y = event.x_root, event.y_root  # Use root coordinates
        logging.info(f"Touch in Idle mode at ({x}, {y})")
    
        
        # Show selection screen instead of directly going to PriceCheck
        self._show_selection_screen()


         
    def _on_selection_background_click(self, event):
        # Clicking on the background does nothing
        pass
        
    def _on_cart_button_click(self, event):
        logging.info("Cart button clicked")
        self._hide_selection_screen()
        # Enter Cart mode
        if hasattr(self, "on_cart_action"):
            self.on_cart_action()
        
    def _on_pc_button_click(self, event):
        logging.info("Price Check button clicked")
        self._hide_selection_screen()
        # Enter PriceCheck mode
        if hasattr(self, "on_touch_action"):
            self.on_touch_action()

    def start(self):
        logging.info("IdleMode: Starting")
        self.is_active = True
        
        # Make sure all overlays are hidden first (in case they weren't properly cleaned up)
        self._hide_all_overlays()
        
        # Re-show label
        self.label.place(x=0, y=0, width=WINDOW_W, height=WINDOW_H)
        self.label.lift()
        
        # Load zipcode and API key from credentials
        self._load_weather_config()
        
        # Update weather data
        self._update_weather()
        
        self.order = self._load_images()
        logging.info("Idle: found %d image(s) in %s", len(self.order), IDLE_DIR)
        random.shuffle(self.order)
        self.idx = 0
        self._show_next()
        
        # Start overlay update timer
        self._update_overlays()
        
        # Start command checker
        self.start_command_checker()
        
        # Start video upload checker
        self.idle_start_time = time.time()
        self._check_and_upload_videos()




    def stop(self):
        logging.info("IdleMode: Stopping")
        self.is_active = False
        
        # Cancel timers
        if self.slide_after:
            self.root.after_cancel(self.slide_after)
            self.slide_after = None
            
        if self.overlay_timer:
            self.root.after_cancel(self.overlay_timer)
            self.overlay_timer = None
            
        if self.selection_timeout:
            self.root.after_cancel(self.selection_timeout)
            self.selection_timeout = None
        
        # Cancel command checker timer
        if hasattr(self, 'command_check_timer') and self.command_check_timer:
            self.root.after_cancel(self.command_check_timer)
            self.command_check_timer = None

        # Cancel video check timer
        if hasattr(self, 'video_check_timer') and self.video_check_timer:
            self.root.after_cancel(self.video_check_timer)
            self.video_check_timer = None
        
        # Cancel restart countdown timer if active
        if hasattr(self, 'restart_countdown_timer') and self.restart_countdown_timer:
            self.root.after_cancel(self.restart_countdown_timer)
            self.restart_countdown_timer = None
        
        # Destroy restart popup if it exists
        if hasattr(self, 'restart_popup') and self.restart_popup:
            self.restart_popup.destroy()
            self.restart_popup = None
    
        
        # Hide all overlays
        self._hide_all_overlays()
        self._hide_selection_screen()

    
        
    def _hide_all_overlays(self):
        """Hide all overlay elements and main label"""
        # Explicitly hide all overlays to ensure they're removed
        for widget in [self.bottom_text, self.time_label, self.weather_label, self.admin_button]:
            widget.place_forget()
        
        self.label.place_forget()
        
        
    def _hide_selection_screen(self):
        """Hide selection screen and return to idle slideshow."""
        if self.selection_timeout:
            self.root.after_cancel(self.selection_timeout)
            self.selection_timeout = None
            
        self.selection_label.place_forget()
        self.cart_button.place_forget()
        self.pc_button.place_forget()
        
        self.selection_active = False
        
        # Only restart slideshow if still in idle mode
        if self.is_active:
            self._show_next()
            self._update_overlays()

    def _load_weather_config(self):
        """Load zipcode and API key from Google Sheet."""
        try:
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/spreadsheets",
            ]
            creds = Credentials.from_service_account_file(str(GS_CRED_PATH), scopes=scopes)
            gc = gspread.authorize(creds)
            sheet = gc.open(GS_SHEET_NAME).worksheet(GS_CRED_TAB)
            self.zipcode = sheet.acell('B29').value
            self.weather_api_key = sheet.acell('B33').value
            logging.info(f"Loaded zipcode: {self.zipcode}, API key available: {bool(self.weather_api_key)}")
        except Exception as e:
            logging.error(f"Failed to load weather config: {e}")
            self.zipcode = None
            self.weather_api_key = None

    def _update_weather(self):
        """Update weather data if needed."""
        current_time = time.time()
        
        # Only update if we have a zipcode, API key and it's time to update
        if (not self.zipcode or not self.weather_api_key or 
            (current_time - self.weather_last_update) < WEATHER_UPDATE_INTERVAL):
            return
            
        try:
            url = f"https://api.openweathermap.org/data/2.5/weather?zip={self.zipcode},us&units=imperial&appid={self.weather_api_key}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                self.weather_data = response.json()
                self.weather_last_update = current_time
                logging.info(f"Updated weather data for {self.weather_data.get('name', 'Unknown')}")
            else:
                logging.error(f"Weather API error: {response.status_code}")
        except Exception as e:
            logging.error(f"Failed to update weather: {e}")

    def _load_images(self):
        IDLE_DIR.mkdir(parents=True, exist_ok=True)
        return [p for p in sorted(IDLE_DIR.iterdir())
                if p.is_file() and p.suffix.lower() in IMAGE_EXTS]

    def _letterbox(self, im: Image.Image):
        """Force letterboxing by scaling to 90% of screen height"""
        # Force some letterboxing by scaling to 90% of screen height
        target_height = int(WINDOW_H * 0.9)
        
        # Calculate width to maintain aspect ratio
        aspect_ratio = im.width / im.height
        target_width = int(target_height * aspect_ratio)
        
        # Ensure width doesn't exceed screen width
        if target_width > WINDOW_W:
            target_width = int(WINDOW_W * 0.9)
            target_height = int(target_width / aspect_ratio)
        
        # Resize image
        resized = im.resize((target_width, target_height), Image.LANCZOS)
        
        # Create black background
        bg = Image.new("RGB", (WINDOW_W, WINDOW_H), (0, 0, 0))
        
        # Paste resized image in center
        x_offset = (WINDOW_W - target_width) // 2
        y_offset = (WINDOW_H - target_height) // 2
        bg.paste(resized, (x_offset, y_offset))
        
        #logging.info(f"Forced letterboxing - Image: {target_width}x{target_height}, " +
                    #f"Letterbox top/bottom: {y_offset}px, left/right: {x_offset}px")
        
        return bg


                

    def _show_next(self):
        if not self.is_active:
            return
            
        if not self.order:
            frame = Image.new("RGB", (WINDOW_W, WINDOW_H), (0, 0, 0))
            d = ImageDraw.Draw(frame)
            msg = f"No images in {IDLE_DIR}"
            w, h = d.textbbox((0,0), msg, font=load_ttf(24))[2:]
            d.text(((WINDOW_W - w)//2, (WINDOW_H - h)//2), msg, font=load_ttf(24), fill=(255,255,255))
        else:
            path = self.order[self.idx]
            #logging.info("Idle: showing %s", path.name)
            self.idx = (self.idx + 1) % len(self.order)
            try:
                with Image.open(path) as im:
                    if im.mode in ("RGBA", "P"):
                        im = im.convert("RGB")
                    frame = self._letterbox(im)
            except Exception as e:
                logging.error("Idle: failed to load %s: %s", path, e)
                frame = Image.new("RGB", (WINDOW_W, WINDOW_H), (0, 0, 0))

        if self.is_active:  # Check again in case mode changed during image loading
            self.tk_img = ImageTk.PhotoImage(frame)
            self.label.configure(image=self.tk_img)
            self.label.lift()
            
            # Schedule next slide
            self.slide_after = self.root.after(SLIDE_MS, self._show_next)


        
    def _lift_overlays(self):
        """Ensure all overlay elements stay on top"""
        # Only lift elements that have been placed
        if self.is_active:  # Only lift if mode is active
            if self.bottom_text.winfo_ismapped():
                self.bottom_text.lift()
            if self.time_label.winfo_ismapped():
                self.time_label.lift()
            if self.weather_label.winfo_ismapped():
                self.weather_label.lift()
            if self.admin_button.winfo_ismapped():
                self.admin_button.lift()



# ==============================
#     UPC NORMALIZATION HELPERS
# ==============================

def _digits_only(s: str) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())

def upc_variants_from_sheet(value: str):
    """
    Generate all reasonable variants for a UPC stored in the sheet.
    Handles cells that lost leading zero or were formatted as numbers.
    Returns a list of unique strings.
    """
    variants = []
    raw = (value or "").strip()
    dig = _digits_only(raw)

    def add(v):
        if v and v not in variants:
            variants.append(v)

    # raw and digits-only
    add(raw)
    add(dig)

    # If the sheet lost a leading zero on a 12-digit UPC (now 11 digits)
    if len(dig) == 11:
        add("0" + dig)             # 12-digit with restored leading zero
    # If the sheet stored 12-digit UPC properly, also add 13-digit EAN with leading 0
    if len(dig) == 12:
        add("0" + dig)             # EAN-13 variant
        add(dig.lstrip("0"))       # also without leading zeros (defensive)
    # If sheet stored EAN-13 that starts with 0, add 12-digit UPC-A
    if len(dig) == 13 and dig.startswith("0"):
        add(dig[1:])
    # If GTIN-14 with leading zeros, add trimmed versions down to 12
    if len(dig) == 14:
        t = dig.lstrip("0")
        add(t)
        if len(t) == 13 and t.startswith("0"):
            add(t[1:])
        if len(t) == 12 and (not t.startswith("0")):
            add("0" + t)  # also add an EAN-13 with leading zero

    return variants

def upc_variants_from_scan(scan: str):
    """
    Generate variants for an incoming scan.
    Most scanners give 12-digit UPC-A or 13-digit EAN-13.
    """
    variants = []
    raw = (scan or "").strip()
    dig = _digits_only(raw)

    def add(v):
        if v and v not in variants:
            variants.append(v)

    add(raw)
    add(dig)

    # If 13 and starts with 0, also try 12
    if len(dig) == 13 and dig.startswith("0"):
        add(dig[1:])
    # If 12 and starts with 0, try without that zero (for sheets that lost it)
    if len(dig) == 12 and dig.startswith("0"):
        add(dig[1:])
    # If 11 (sheet lost zero scenario), try adding a leading zero
    if len(dig) == 11:
        add("0" + dig)
    # If 14, trim leading zeros down to 13/12
    if len(dig) == 14:
        t = dig.lstrip("0")
        add(t)
        if len(t) == 13 and t.startswith("0"):
            add(t[1:])

    return variants


# ==============================
#   GOOGLE DRIVE IMAGE LOADER
# ==============================

class GoogleDriveImageLoader:
    """Handles loading images from Google Drive folder with caching."""

    def __init__(self, credentials_path, folder_id):
        self.folder_id = folder_id
        self.cache_dir = Path.home() / "SelfCheck" / "ImageCache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.file_map = {}  # filename -> file_id mapping
        self.drive_service = None
        self._init_drive_service(credentials_path)

    def _init_drive_service(self, credentials_path):
        """Initialize Google Drive API service."""
        try:
            scopes = [
                "https://www.googleapis.com/auth/drive.readonly",
            ]
            creds = Credentials.from_service_account_file(str(credentials_path), scopes=scopes)
            self.drive_service = build('drive', 'v3', credentials=creds)
            self._build_file_map()
            logging.info("Google Drive service initialized successfully")
        except Exception as e:
            logging.error("Failed to initialize Google Drive service: %s", e)
            self.drive_service = None

    def _build_file_map(self):
        """Build a mapping of filename to file_id for the specified folder."""
        if not self.drive_service:
            return

        try:
            query = f"'{self.folder_id}' in parents and trashed=false"
            results = self.drive_service.files().list(
                q=query,
                fields="files(id, name)"
            ).execute()

            files = results.get('files', [])
            self.file_map = {file['name']: file['id'] for file in files}
            logging.info("Found %d files in Google Drive folder", len(self.file_map))

        except Exception as e:
            logging.error("Failed to build file map from Google Drive: %s", e)

    def get_image(self, filename):
        """
        Get image from Google Drive, with local caching.
        Returns PIL Image object or None if not found.
        """
        if not filename or not self.drive_service:
            return None

        # Check local cache first
        cache_path = self.cache_dir / filename
        if cache_path.exists():
            try:
                return Image.open(cache_path)
            except Exception as e:
                logging.warning("Failed to load cached image %s: %s", filename, e)
                # Remove corrupted cache file
                try:
                    cache_path.unlink()
                except:
                    pass

        # Download from Google Drive
        file_id = self.file_map.get(filename)
        if not file_id:
            logging.warning("File not found in Google Drive: %s", filename)
            return None

        try:
            # Download file content
            request = self.drive_service.files().get_media(fileId=file_id)
            file_content = io.BytesIO()

            import googleapiclient.http
            downloader = googleapiclient.http.MediaIoBaseDownload(file_content, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()

            # Save to cache
            file_content.seek(0)
            with open(cache_path, 'wb') as f:
                f.write(file_content.read())

            # Load as PIL Image
            file_content.seek(0)
            image = Image.open(file_content)
            logging.info("Downloaded and cached image: %s", filename)
            return image

        except Exception as e:
            logging.error("Failed to download image %s from Google Drive: %s", filename, e)
            return None


# ==============================
#   GOOGLE SHEETS LOADER (UPC)
# ==============================

def load_inventory_by_upc():
    """Build a dict of *many* UPC variants -> the same row list."""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_file(str(GS_CRED_PATH), scopes=scopes)
    gc = gspread.authorize(creds)
    logging.info("Connecting to Google Sheet: %s / Tab: %s", GS_SHEET_NAME, GS_TAB)

    try:
        ws = gc.open(GS_SHEET_NAME).worksheet(GS_TAB)
        rows = ws.get_all_values()
    except Exception as e:
        logging.error("PriceCheck: sheet open/read error: %s", e)
        return {}

    logging.info("PriceCheck: loaded %d rows from sheet", len(rows))
    if not rows:
        return {}

    header = rows[0]
    logging.info("PriceCheck: header row: %s", header)

    index = {}
    collisions = 0
    for r in rows[1:]:
        if not r:
            continue
        raw_upc = (r[0] if len(r) > 0 else "").strip()
        if not raw_upc:
            continue
        for v in upc_variants_from_sheet(raw_upc):
            if v in index and index[v] is not r:
                collisions += 1
            index[v] = r

    logging.info("PriceCheck: indexed %d UPC keys (including variants), collisions=%d",
                 len(index), collisions)
    for i, k in enumerate(list(index.keys())[:5]):
        logging.info("PriceCheck: sample key %d: %r", i+1, k)
    return index


# ==============================
#        PRICECHECK MODE
# ==============================

class PriceCheckMode:
    """
    Background = PriceCheck.png.
    Waits for barcode scans (USB keyboard wedge).
    Looks up UPC in Google Sheet 'Inventory1001'/'Inv'.
    Overlays text in the blue box and product image (from Column L) in the green box.
    """
    # Column indices (0-based) for A..L:
    IDX_B = 1
    IDX_C = 2
    IDX_E = 4
    IDX_F = 5
    IDX_G = 6
    IDX_H = 7
    IDX_I = 8
    IDX_K = 10
    IDX_L = 11

    def __init__(self, root: tk.Tk):
        self.root = root
        self.label = tk.Label(root, bg="black")
        self.label.place(x=0, y=0, width=WINDOW_W, height=WINDOW_H)

        self.tk_img = None
        self.base_bg = None
        self.inv = {}
        self.last_activity_ts = time.time()
        self.timeout_after = None

        # Initialize Google Drive image loader
        self.image_loader = GoogleDriveImageLoader(GS_CRED_PATH, GDRIVE_FOLDER_ID)

        # Define touch handler inside __init__
        def touch_handler(event):
            x, y = event.x, event.y
            logging.info(f"Touch in Cart mode at ({x}, {y})")
            self.last_activity_ts = time.time()
    
        # Bind the touch handler
        self.label.bind("<Button-1>", self._on_touch)

        # Hidden entry to capture scanner input - create once and reuse
        self.scan_var = tk.StringVar()
        self.scan_entry = tk.Entry(root, textvariable=self.scan_var)
        # Keep it hidden initially
        self.scan_entry.place(x=-1000, y=-1000, width=10, height=10)

        # Bind events once during initialization
        self.scan_entry.bind("<Return>", self._on_scan_submit)
        self.scan_entry.bind("<KP_Enter>", self._on_scan_submit)

        # Add debugging - monitor when text changes
        self.scan_var.trace_add("write", self._on_scan_var_change)

        # Add touch support
        self.label.bind("<Button-1>", self._on_touch)

    def _on_touch(self, event):
        """Touch handler for PriceCheck mode"""
        # Touch handler for PriceCheck mode
        x, y = event.x, event.y
        logging.info(f"Touch in PriceCheck mode at ({x}, {y})")

        # Define the button area
        button_area = (WINDOW_W//2 - 150, WINDOW_H - 100, WINDOW_W//2 + 150, WINDOW_H - 20)
        
        # Check if touch is in the button area
        if (button_area[0] <= x <= button_area[2] and
            button_area[1] <= y <= button_area[3]):
            # Start Transaction button clicked
            logging.info("Start Transaction button clicked")
            if hasattr(self, "on_cart_action"):
                self.on_cart_action()


    def _on_scan_var_change(self, *args):
        """Debug callback to see when scanner input is received"""
        current_value = self.scan_var.get()
        if current_value:
            logging.info("Scanner input detected: %r", current_value)

    def start(self):
        logging.info("PriceCheck: Starting mode")
        # Make visible when entering PriceCheck
        self.label.place(x=0, y=0, width=WINDOW_W, height=WINDOW_H)
        self.label.lift()

        self.base_bg = self._load_bg()
        self._render_base()
        try:
            # Only reload inventory if we don't have it already
            if not self.inv:
                self.inv = load_inventory_by_upc()
        except Exception as e:
            self.inv = {}
            self._overlay_notice(f"Sheet error:\n{e}")

        self._reset_for_next_scan()
        self._arm_timeout()

    def stop(self):
        logging.info("PriceCheck: Stopping mode")
        if self.timeout_after:
            self.root.after_cancel(self.timeout_after)
            self.timeout_after = None
        # Hide when leaving PriceCheck
        self.label.place_forget()
        # Don't unbind events - keep them bound for reuse
        # Just move entry further off-screen
        self.scan_entry.place(x=-2000, y=-2000, width=1, height=1)

    # ---- UI helpers ----
    def _load_bg(self):
        if PRICE_BG_PATH.exists():
            try:
                with Image.open(PRICE_BG_PATH) as im:
                    if im.mode in ("RGBA", "P"):
                        im = im.convert("RGB")
                    return self._letterbox(im)
            except Exception:
                pass
        # fallback white
        return Image.new("RGB", (WINDOW_W, WINDOW_H), (255, 255, 255))

    def _letterbox(self, im: Image.Image):
        iw, ih = im.size
        scale = min(WINDOW_W/iw, WINDOW_H/ih)
        nw, nh = int(iw*scale), int(ih*scale)
        resized = im.resize((nw, nh), Image.LANCZOS)
        bg = Image.new("RGB", (WINDOW_W, WINDOW_H), (255,255,255))
        bg.paste(resized, ((WINDOW_W-nw)//2, (WINDOW_H-nh)//2))
        return bg

    def _render_base(self):
        self.tk_img = ImageTk.PhotoImage(self.base_bg)
        self.label.configure(image=self.tk_img)
        self.label.lift()

    def _overlay_notice(self, msg):
        frame = self.base_bg.copy()
        d = ImageDraw.Draw(frame)
        x1,y1,x2,y2 = PC_BLUE_BOX
        # No border rectangle
        w,h = d.textbbox((0,0), msg, font=PC_FONT_SUB)[2:]
        d.text((x1 + (x2-x1-w)//2, y1 + (y2-y1-h)//2), msg, font=PC_FONT_SUB, fill=(0,0,0))

        # Change button text and style
        button_text = "Start Transaction"
        bw, bh = d.textbbox((0,0), button_text, font=PC_FONT_SUB)[2:]
        button_x = WINDOW_W//2 - bw//2
        button_y = WINDOW_H - 80
        d.rectangle([button_x-20, button_y-10, button_x+bw+20, button_y+bh+10],
                   fill=(0,150,0), outline=(0,0,0), width=2)  # Changed color to green
        d.text((button_x, button_y), button_text, font=PC_FONT_SUB, fill=(255,255,255))

        self.tk_img = ImageTk.PhotoImage(frame)
        self.label.configure(image=self.tk_img)
        self.label.lift()


    def _overlay_result(self, row_list):
        frame = self.base_bg.copy()
        d = ImageDraw.Draw(frame)
        bx1,by1,bx2,by2 = PC_BLUE_BOX

        # Move green box up by about 1 inch (96 pixels at 96 DPI, using 72 pixels for safety)
        gx1,gy1,gx2,gy2 = PC_GREEN_BOX
        gy1 -= 72  # Move up by ~1 inch
        gy2 -= 72  # Move up by ~1 inch

        def col(idx):
            return (row_list[idx] if len(row_list) > idx else "").strip()

        # Texts from columns
        title = col(self.IDX_B)
        sub   = col(self.IDX_C)
        size  = col(self.IDX_E)
        cal   = col(self.IDX_F)
        sug   = col(self.IDX_G)
        sod   = col(self.IDX_H)
        lineI = col(self.IDX_I)
        onhand= col(self.IDX_K)
        picnm = col(self.IDX_L)

        # Blue area content (no border)
        d.text((bx1+12, by1+10), title, font=PC_FONT_TITLE, fill=(0,0,0))
        d.text((bx1+12, by1+10 + 50), sub, font=PC_FONT_SUB, fill=(0,0,0))
        d.text((bx1+12, by1+10 + 50 + 30),
               f"Size: {size}  Calories: {cal}  Sugar: {sug}  Sodium: {sod}",
               font=PC_FONT_INFO, fill=(0,0,0))
        d.text((bx1+12, by1+10 + 50 + 30 + 26),
               lineI, font=PC_FONT_LINE, fill=(0,0,0))
        d.text((bx1+12, by2 - 28),
               f"Amount on hand: {onhand}", font=PC_FONT_SMALL, fill=(0,0,0))

        # Product image into green box from Google Drive (moved up 1 inch)
        if picnm:
            try:
                pim = self.image_loader.get_image(picnm)
                if pim:
                    if pim.mode in ("RGBA","P"):
                        pim = pim.convert("RGB")
                    gw, gh = gx2-gx1, gy2-gy1
                    scale = min(gw/pim.width, gh/pim.height)
                    nw, nh = max(1,int(pim.width*scale)), max(1,int(pim.height*scale))
                    pim = pim.resize((nw, nh), Image.LANCZOS)
                    ox = gx1 + (gw - nw)//2
                    oy = gy1 + (gh - nh)//2
                    frame.paste(pim, (ox, oy))
                    logging.info("Displayed product image: %s", picnm)
                else:
                    logging.warning("Could not load product image: %s", picnm)
            except Exception as e:
                logging.error("Error loading product image %s: %s", picnm, e)

        # Change button text and style
        button_text = "Start Transaction"
        bw, bh = d.textbbox((0,0), button_text, font=PC_FONT_SUB)[2:]
        button_x = WINDOW_W//2 - bw//2
        button_y = WINDOW_H - 80
        d.rectangle([button_x-20, button_y-10, button_x+bw+20, button_y+bh+10],
                   fill=(0,150,0), outline=(0,0,0), width=2)  # Changed color to green
        d.text((button_x, button_y), button_text, font=PC_FONT_SUB, fill=(255,255,255))

        self.tk_img = ImageTk.PhotoImage(frame)
        self.label.configure(image=self.tk_img)
        self.label.lift()

    # ---- Scanner handling ----
    def _on_scan_submit(self, _event=None):
        upc = self.scan_var.get().strip()
        logging.info("Scan submit called with: %r", upc)
        self.scan_var.set("")
        self.last_activity_ts = time.time()
        if not upc:
            self._overlay_notice("No scan")
            return

        tried = upc_variants_from_scan(upc)
        logging.info("Scan received: %r -> trying variants: %s", upc, tried)

        row = None
        for v in tried:
            row = self.inv.get(v)
            if row:
                logging.info("Match on variant: %r", v)
                break

        if not row:
            self._overlay_notice(f"Not found:\n{upc}")
            return

        self._overlay_result(row)

    def _reset_for_next_scan(self):
        logging.info("PriceCheck: Resetting for next scan")
        self.last_activity_ts = time.time()
        self.scan_var.set("")

        # Multiple attempts to ensure focus
        self.scan_entry.place(x=-1000, y=-1000, width=10, height=10)
        self.root.update_idletasks()

        # Try multiple focus methods
        self.scan_entry.focus_set()
        self.root.after(50, lambda: self.scan_entry.focus_force())
        self.root.after(100, lambda: self.scan_entry.focus_set())

        # Log current focus for debugging
        self.root.after(200, self._debug_focus)

        self._overlay_notice("Scan an item")

    def _debug_focus(self):
        focused = self.root.focus_get()
        logging.info("Current focus widget: %s", focused)
        logging.info("Scan entry widget: %s", self.scan_entry)
        logging.info("Focus matches scan entry: %s", focused == self.scan_entry)

    def _arm_timeout(self):
        """Set up inactivity timeout for admin mode."""
        if self.timeout_after:
            self.root.after_cancel(self.timeout_after)

        def check_timeout():
            current_time = time.time()
            elapsed = current_time - self.last_activity_ts
            logging.debug(f"Admin timeout check: {elapsed:.1f}s elapsed")

            if elapsed >= (ADMIN_TIMEOUT_MS/1000.0):
                logging.info(f"Admin mode timeout after {elapsed:.1f}s - returning to Idle")
                if hasattr(self, "on_timeout"):
                    self.on_timeout()
                return
            self.timeout_after = self.root.after(1000, check_timeout)

        self.timeout_after = self.root.after(1000, check_timeout)



# ==============================
#          Admin Login Screen
# ==============================
class AdminLoginScreen:
    """Login screen for Admin mode with virtual keyboard."""
    def __init__(self, root: tk.Tk):
        self.root = root
        self.frame = tk.Frame(root, bg="#2c3e50")
        self.frame.place(x=0, y=0, width=WINDOW_W, height=WINDOW_H)

        # Login variables
        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.current_field = None
        self.login_in_progress = False


        # Create login UI
        self._create_login_ui()

    def _create_login_ui(self):
        # Title
        title_label = tk.Label(self.frame, text="Admin Login",
                              font=("Arial", 36, "bold"), bg="#2c3e50", fg="white")
        title_label.pack(pady=(100, 50))

        # Login form
        form_frame = tk.Frame(self.frame, bg="#2c3e50")
        form_frame.pack(pady=20)

        # Username
        username_label = tk.Label(form_frame, text="Username:",
                                 font=("Arial", 18), bg="#2c3e50", fg="white")
        username_label.grid(row=0, column=0, sticky="w", padx=10, pady=10)

        self.username_entry = tk.Entry(form_frame, textvariable=self.username_var,
                                     font=("Arial", 18), width=20)
        self.username_entry.grid(row=0, column=1, padx=10, pady=10)

        # Password
        password_label = tk.Label(form_frame, text="Password:",
                                 font=("Arial", 18), bg="#2c3e50", fg="white")
        password_label.grid(row=1, column=0, sticky="w", padx=10, pady=10)

        self.password_entry = tk.Entry(form_frame, textvariable=self.password_var,
                                     font=("Arial", 18), width=20, show="â€¢")
        self.password_entry.grid(row=1, column=1, padx=10, pady=10)

        # Login button
        self.login_button = tk.Button(form_frame, text="Login", font=("Arial", 18),
                                    bg="#3498db", fg="white", width=10,
                                    command=self._login)
        self.login_button.grid(row=2, column=0, columnspan=2, pady=30)

        # Cancel button
        self.cancel_button = tk.Button(form_frame, text="Cancel", font=("Arial", 18),
                                     bg="#e74c3c", fg="white", width=10,
                                     command=self._cancel)
        self.cancel_button.grid(row=3, column=0, columnspan=2, pady=10)

        # Status message
        self.status_label = tk.Label(form_frame, text="", font=("Arial", 14),
                                   bg="#2c3e50", fg="#e74c3c")
        self.status_label.grid(row=4, column=0, columnspan=2, pady=10)

        # Create virtual keyboard
        self._create_keyboard()

        # Set focus to username field and bind click events
        self.username_entry.focus_set()
        self.current_field = self.username_entry

        self.username_entry.bind("<Button-1>", lambda e: self._set_current_field(self.username_entry))
        self.password_entry.bind("<Button-1>", lambda e: self._set_current_field(self.password_entry))

    def _create_keyboard(self):
        keyboard_frame = tk.Frame(self.frame, bg="#34495e")
        keyboard_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=20)

        # Track shift state
        self.shift_on = False

        # Define keyboard layouts
        self.keys_lower = [
            ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
            ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
            ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l'],
            ['z', 'x', 'c', 'v', 'b', 'n', 'm', '.', '@']
        ]

        self.keys_upper = [
            ['!', '@', '#', '$', '%', '^', '&', '*', '(', ')'],
            ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
            ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L'],
            ['Z', 'X', 'C', 'V', 'B', 'N', 'M', ',', '_']
        ]

        # Create keyboard rows frames
        self.key_buttons = []
        self.row_frames = []

        for i in range(4):
            row_frame = tk.Frame(keyboard_frame, bg="#34495e")
            row_frame.pack(pady=5)
            self.row_frames.append(row_frame)
            self.key_buttons.append([])

        # Populate with initial lowercase keys
        self._update_keyboard_layout()

        # Special keys row
        special_frame = tk.Frame(keyboard_frame, bg="#34495e")
        special_frame.pack(pady=5)

        # Shift key
        self.shift_button = tk.Button(special_frame, text="Shift", font=("Arial", 18),
                                   width=6, height=1, bg="#9b59b6", fg="white",
                                   command=self._toggle_shift)
        self.shift_button.pack(side=tk.LEFT, padx=3)

        # Space
        space_button = tk.Button(special_frame, text="Space", font=("Arial", 18),
                               width=14, height=1, bg="#7f8c8d", fg="white",
                               command=lambda: self._key_press(" "))
        space_button.pack(side=tk.LEFT, padx=3)

        # Symbols
        symbols_button = tk.Button(special_frame, text="123", font=("Arial", 18),
                                 width=4, height=1, bg="#3498db", fg="white",
                                 command=self._show_symbols)
        symbols_button.pack(side=tk.LEFT, padx=3)

        # Backspace
        backspace_button = tk.Button(special_frame, text="â†", font=("Arial", 18),
                                   width=4, height=1, bg="#e67e22", fg="white",
                                   command=self._backspace)
        backspace_button.pack(side=tk.LEFT, padx=3)

        # Clear
        clear_button = tk.Button(special_frame, text="Clear", font=("Arial", 18),
                               width=5, height=1, bg="#e74c3c", fg="white",
                               command=self._clear_field)
        clear_button.pack(side=tk.LEFT, padx=3)

    def _update_keyboard_layout(self):
        """Update keyboard buttons based on shift state"""
        keys = self.keys_upper if self.shift_on else self.keys_lower

        # Clear existing buttons
        for row in self.key_buttons:
            for btn in row:
                btn.destroy()
            row.clear()

        # Create new buttons
        for row_idx, row_keys in enumerate(keys):
            for key in row_keys:
                key_button = tk.Button(self.row_frames[row_idx], text=key, font=("Arial", 18),
                                     width=3, height=1, bg="#7f8c8d", fg="white",
                                     command=lambda k=key: self._key_press(k))
                key_button.pack(side=tk.LEFT, padx=3)
                self.key_buttons[row_idx].append(key_button)

    def _toggle_shift(self):
        """Toggle between uppercase and lowercase keyboard"""
        self.shift_on = not self.shift_on
        self.shift_button.config(bg="#9b59b6" if self.shift_on else "#7f8c8d")
        self._update_keyboard_layout()

    def _show_symbols(self):
        """Show symbol keyboard (could be expanded with a full symbol set)"""
        # For now, we'll just toggle shift as a simple implementation
        self._toggle_shift()

    def _set_current_field(self, field):
        self.current_field = field
        field.focus_set()

    def _key_press(self, key):
        if self.current_field:
            current_text = self.current_field.get()
            self.current_field.delete(0, tk.END)
            self.current_field.insert(0, current_text + key)

    def _backspace(self):
        if self.current_field:
            current_text = self.current_field.get()
            if current_text:
                self.current_field.delete(0, tk.END)
                self.current_field.insert(0, current_text[:-1])

    def _clear_field(self):
        if self.current_field:
            self.current_field.delete(0, tk.END)

    def _login(self):
        if self.login_in_progress:
            return

        self.login_in_progress = True
        self.status_label.config(text="Verifying...")
        self.login_button.config(state=tk.DISABLED)

        username = self.username_var.get().strip()
        password = self.password_var.get().strip()

        if not username or not password:
            self.status_label.config(text="Please enter both username and password")
            self.login_button.config(state=tk.NORMAL)
            self.login_in_progress = False
            return

        # Schedule the actual login check to allow UI to update
        self.root.after(100, lambda: self._verify_credentials(username, password))

    def _verify_credentials(self, username, password):
        try:
            # Connect to Google Sheet with expanded scopes
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/spreadsheets",
            ]
            creds = Credentials.from_service_account_file(str(GS_CRED_PATH), scopes=scopes)
            gc = gspread.authorize(creds)

            # Get login tab
            sheet = gc.open(GS_SHEET_NAME).worksheet(GS_LOGIN_TAB)

            # Get all usernames and passwords (skip header row)
            users = sheet.col_values(1)[1:]  # Column A (usernames)
            passes = sheet.col_values(2)[1:]  # Column B (passwords)

            # Check credentials
            for i, user in enumerate(users):
                if user == username and i < len(passes) and passes[i] == password:
                    logging.info(f"Successful login for user: {username}")
                    if hasattr(self, "on_login_success"):
                        self.on_login_success()
                    return

            # If we get here, login failed
            logging.warning(f"Failed login attempt for user: {username}")
            self.status_label.config(text="Access denied. Contact your system administrator.")
            self.login_button.config(state=tk.NORMAL)
            self.login_in_progress = False

            # Return to idle mode after delay
            self.root.after(3000, self._login_failed)

        except Exception as e:
            logging.error(f"Login verification error: {e}")
            self.status_label.config(text=f"Login error: {str(e)}")
            self.login_button.config(state=tk.NORMAL)
            self.login_in_progress = False

    def _login_failed(self):
        if hasattr(self, "on_login_failed"):
            self.on_login_failed()

    def _cancel(self):
        """Cancel login and return to idle mode."""
        if hasattr(self, "on_login_cancel"):
            self.on_login_cancel()


    def show(self):
        self.frame.lift()
        self.username_entry.focus_set()
        self.current_field = self.username_entry

    def hide(self):
        self.frame.place_forget()



# ==============================
#          Admin Mode
# ==============================

class AdminMode:
    """
    Admin mode for updating credentials and settings.
    Displays Admin.png with text overlay for options.
    """
    def __init__(self, root: tk.Tk):
        self.root = root
        self.label = tk.Label(root, bg="black")
        
        self.tk_img = None
        self.base_bg = None
        self.update_in_progress = False
        self.last_activity_ts = time.time()
        self.timeout_after = None
        self.current_menu = "main"  # Track current menu: "main", "credentials", "wireless"
        
        # Create login screen
        self.login_screen = None  # Will be created in start()
        
        # Add touch support
        self.label.bind("<Button-1>", self._on_touch)
        self.label.bind("<Motion>", self._on_activity)

    


    def _on_touch(self, event):
        """Touch handler for Admin mode"""
        x, y = event.x, event.y
        logging.info(f"Touch in Admin mode at ({x}, {y})")
        self._on_activity()
        
        # Check which menu we're in
        if self.current_menu == "main":
            # Main menu button areas
            # Credentials button
            if 80 <= x <= 780 and 300 <= y <= 370:
                self.current_menu = "credentials"
                self._render_credentials_menu()
                
            # Wireless button
            elif 80 <= x <= 780 and 400 <= y <= 470:
                self.current_menu = "wireless"
                self._render_wireless_menu()
                
            # System Settings button
            elif 80 <= x <= 780 and 500 <= y <= 570:
                self.current_menu = "system_settings"
                self._render_system_settings_menu()
                
            # Exit button (moved down)
            elif 80 <= x <= 780 and 600 <= y <= 670:
                if hasattr(self, "on_exit"):
                    self.on_exit()
                    
            # System Restart button (moved down)
            elif 80 <= x <= 780 and 700 <= y <= 770:
                self._system_restart()


        
        elif self.current_menu == "credentials":
            # Credentials submenu button areas
            # Update credentials button
            if 80 <= x <= 780 and 300 <= y <= 370:
                self.update_credentials()
                
            # Update location files button
            elif 80 <= x <= 780 and 400 <= y <= 470:
                self.update_location_files()
                
            # Back button
            elif 80 <= x <= 380 and 500 <= y <= 570:
                self.current_menu = "main"
                self._render_menu()
        
        elif self.current_menu == "wireless":
            # Wireless submenu button areas
            # WiFi settings button
            if 80 <= x <= 780 and 300 <= y <= 370:
                self.open_wifi_settings()
                
            # Local IP button
            elif 80 <= x <= 780 and 400 <= y <= 470:
                self.show_local_ip()
                
            # Bluetooth button
            elif 80 <= x <= 780 and 500 <= y <= 570:
                self.open_bluetooth_settings()
                
            # Back button
            elif 80 <= x <= 380 and 600 <= y <= 670:
                self.current_menu = "main"
                self._render_menu()
                
        elif self.current_menu == "system_settings":
            # Check if a setting button was clicked
            for button in self.settings_buttons:
                x1, y1, x2, y2 = button["rect"]
                if x1 <= x <= x2 and y1 <= y <= y2:
                    # Toggle the button status
                    if button["status"] == "Enable":
                        button["status"] = "Disable"
                        # Update the current_settings dictionary
                        if button["option"] == "Venmo Payments":
                            self.current_settings["payment_options"]["venmo_enabled"] = False
                        elif button["option"] == "CashApp Payments":
                            self.current_settings["payment_options"]["cashapp_enabled"] = False
                        elif button["option"] == "Receipt Printer":
                            self.current_settings["receipt_options"]["print_receipt_enabled"] = False
                        elif button["option"] == "Security Camera":
                            self.current_settings["camera_options"]["security_camera_enabled"] = False
                    else:
                        button["status"] = "Enable"
                        # Update the current_settings dictionary
                        if button["option"] == "Venmo Payments":
                            self.current_settings["payment_options"]["venmo_enabled"] = True
                        elif button["option"] == "CashApp Payments":
                            self.current_settings["payment_options"]["cashapp_enabled"] = True
                        elif button["option"] == "Receipt Printer":
                            self.current_settings["receipt_options"]["print_receipt_enabled"] = True
                        elif button["option"] == "Security Camera":
                            self.current_settings["camera_options"]["security_camera_enabled"] = True
                    # Re-render the menu with updated status
                    self._render_system_settings_menu()
                    return
            
            # Check if Save & Exit button was clicked
            if hasattr(self, 'save_button_rect'):
                x1, y1, x2, y2 = self.save_button_rect
                if x1 <= x <= x2 and y1 <= y <= y2:
                    self._save_settings()
                    return
        
        # Back button (in status screens)
        elif 80 <= x <= 480 and 500 <= y <= 570:
            # Only active in status screens
            if self.update_in_progress == False and hasattr(self, "back_to_menu"):
                if self.current_menu == "main":
                    self._render_menu()
                elif self.current_menu == "credentials":
                    self._render_credentials_menu()
                elif self.current_menu == "wireless":
                    self._render_wireless_menu()



    def _render_system_settings_menu(self):
        """Render the system settings menu."""
        if not hasattr(self, 'base_bg') or self.base_bg is None:
            logging.error("Cannot render system settings menu: base_bg is None")
            self.base_bg = Image.new("RGB", (WINDOW_W, WINDOW_H), (255, 255, 255))
        
        try:
            frame = self.base_bg.copy()
            d = ImageDraw.Draw(frame)
            
            # Add title
            title_font = load_ttf(48)
            title_text = "System Settings"
            tw, th = d.textbbox((0,0), title_text, font=title_font)[2:]
            d.text(((WINDOW_W - tw)//2, 100), title_text, font=title_font, fill=(0,0,0))
            
            # Load current settings
            settings_path = Path.home() / "SelfCheck" / "Cred" / "Settings.json"
            try:
                with open(settings_path, 'r') as f:
                    settings = json.load(f)
            except Exception as e:
                logging.error(f"Error loading settings: {e}")
                settings = {
                    "payment_options": {
                        "venmo_enabled": True,
                        "cashapp_enabled": True
                    },
                    "receipt_options": {
                        "print_receipt_enabled": True
                    },
                    "camera_options": {
                        "security_camera_enabled": True
                    }
                }
            
            # Store current settings for button rendering
            if not hasattr(self, 'current_settings'):
                self.current_settings = settings
            
            # Menu options - with touch-friendly buttons
            option_font = load_ttf(40)
            
            # Settings buttons with current status
            venmo_status = "Enable" if self.current_settings["payment_options"]["venmo_enabled"] else "Disable"
            cashapp_status = "Enable" if self.current_settings["payment_options"]["cashapp_enabled"] else "Disable"
            printer_status = "Enable" if self.current_settings["receipt_options"]["print_receipt_enabled"] else "Disable"
            
            # Add camera status
            if "camera_options" not in self.current_settings:
                self.current_settings["camera_options"] = {"security_camera_enabled": True}
            camera_status = "Enable" if self.current_settings["camera_options"]["security_camera_enabled"] else "Disable"
            
            settings_options = [
                {"text": "Venmo Payments", "status": venmo_status, "y": 250, "color": (0,120,200)},
                {"text": "CashApp Payments", "status": cashapp_status, "y": 350, "color": (0,150,100)},
                {"text": "Receipt Printer", "status": printer_status, "y": 450, "color": (100,100,200)},
                {"text": "Security Camera", "status": camera_status, "y": 550, "color": (150,50,150)}
            ]
            
            # Store button positions for touch detection
            self.settings_buttons = []
            
            for option in settings_options:
                option_x, option_y = 100, option["y"]
                text_w, text_h = d.textbbox((0,0), option["text"], font=option_font)[2:]
                
                # Draw option text
                d.text((option_x, option_y), option["text"], font=option_font, fill=(0,0,0))
                
                # Draw status button
                button_x = option_x + text_w + 100  # Position button to the right of text
                button_w = 200
                button_h = text_h + 20
                
                # Choose button color based on status
                if option["status"] == "Enable":
                    button_color = (0, 150, 0)  # Green for enabled
                else:
                    button_color = (150, 0, 0)  # Red for disabled
                    
                # Draw button
                d.rectangle([button_x, option_y-10, button_x+button_w, option_y+button_h], 
                           fill=button_color, outline=(0,0,0), width=2)
                d.text((button_x+20, option_y), option["status"], font=option_font, fill=(255,255,255))
                
                # Store button position and option info for touch detection
                self.settings_buttons.append({
                    "rect": (button_x, option_y-10, button_x+button_w, option_y+button_h),
                    "option": option["text"],
                    "status": option["status"]
                })
            
            # Save & Exit button
            save_btn_y = 650  # Move down to accommodate new button
            save_btn_text = "Save & Exit"
            save_text_w, save_text_h = d.textbbox((0,0), save_btn_text, font=option_font)[2:]
            save_btn_x = (WINDOW_W - save_text_w) // 2 - 50  # Center the button
            save_btn_w = save_text_w + 100
            save_btn_h = save_text_h + 20
            
            d.rectangle([save_btn_x, save_btn_y-10, save_btn_x+save_btn_w, save_btn_y+save_btn_h], 
                       fill=(0,120,200), outline=(0,0,0), width=2)
            d.text((save_btn_x+50, save_btn_y), save_btn_text, font=option_font, fill=(255,255,255))
            
            # Store save button position
            self.save_button_rect = (save_btn_x, save_btn_y-10, save_btn_x+save_btn_w, save_btn_y+save_btn_h)
            
            self.tk_img = ImageTk.PhotoImage(frame)
            self.label.configure(image=self.tk_img)
            self.label.lift()
            
            # Reset the back_to_menu flag
            if hasattr(self, 'back_to_menu'):
                delattr(self, 'back_to_menu')
                
        except Exception as e:
            logging.error(f"Error rendering system settings menu: {e}")
            import traceback
            logging.error(traceback.format_exc())


    def _save_settings(self):
        """Save current settings to JSON file and Google Sheets."""
        if not hasattr(self, 'current_settings'):
            logging.error("No settings found to save")
            self._show_error_popup("No settings found to save")
            return
        
        try:
            # Save to JSON file
            settings_path = Path.home() / "SelfCheck" / "Cred" / "Settings.json"
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(settings_path, 'w') as f:
                json.dump(self.current_settings, f, indent=4)
                
            # Update Google Sheets
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_file(str(GS_CRED_PATH), scopes=scopes)
            gc = gspread.authorize(creds)
            
            # Open the Settings tab
            sheet = gc.open(GS_SHEET_NAME).worksheet("Settings")
            
            # Update cells - use batch update instead of individual updates
            venmo_status = "Enable" if self.current_settings["payment_options"]["venmo_enabled"] else "Disable"
            cashapp_status = "Enable" if self.current_settings["payment_options"]["cashapp_enabled"] else "Disable"
            printer_status = "Enable" if self.current_settings["receipt_options"]["print_receipt_enabled"] else "Disable"
            camera_status = "Enable" if self.current_settings["camera_options"]["security_camera_enabled"] else "Disable"
            
            # Use batch update with proper format
            sheet.update_cell(2, 2, venmo_status)     # B2
            sheet.update_cell(3, 2, cashapp_status)   # B3
            sheet.update_cell(4, 2, printer_status)   # B4
            sheet.update_cell(5, 2, camera_status)    # B5
            
            # Show confirmation popup
            self._show_settings_saved_popup()
            
        except Exception as e:
            logging.error(f"Error saving settings: {e}")
            import traceback
            logging.error(traceback.format_exc())
            
            # Show error popup
            self._show_error_popup("Error saving settings")


    

    def _show_settings_saved_popup(self):
        """Show confirmation popup for saved settings."""
        # Create popup frame
        popup = tk.Frame(self.root, bg="white", bd=3, relief=tk.RAISED)
        popup.place(relx=0.5, rely=0.5, width=500, height=300, anchor=tk.CENTER)
        
        # Title
        title_label = tk.Label(popup, text="Settings Saved", 
                             font=("Arial", 24, "bold"), bg="white")
        title_label.pack(pady=(40, 20))
        
        # Message
        message_label = tk.Label(popup, 
                               text="System needs to be restarted\nfor changes to take effect", 
                               font=("Arial", 18), bg="white")
        message_label.pack(pady=20)
        
        # OK button
        ok_btn = tk.Button(popup, text="OK", font=("Arial", 18), bg="#3498db", fg="white",
                         width=10, command=lambda: self._close_popup_and_return(popup))
        ok_btn.pack(pady=20)

    def _show_error_popup(self, message):
        """Show error popup."""
        # Create popup frame
        popup = tk.Frame(self.root, bg="white", bd=3, relief=tk.RAISED)
        popup.place(relx=0.5, rely=0.5, width=500, height=300, anchor=tk.CENTER)
        
        # Title
        title_label = tk.Label(popup, text="Error", 
                             font=("Arial", 24, "bold"), bg="white", fg="red")
        title_label.pack(pady=(40, 20))
        
        # Message
        message_label = tk.Label(popup, text=message, 
                               font=("Arial", 18), bg="white")
        message_label.pack(pady=20)
        
        # OK button - return to main menu when clicked
        ok_btn = tk.Button(popup, text="OK", font=("Arial", 18), bg="#3498db", fg="white",
                         width=10, command=lambda: self._close_popup_and_return(popup))
        ok_btn.pack(pady=20)


    def _close_popup_and_return(self, popup):
        """Close popup and return to main menu."""
        popup.destroy()
        self.current_menu = "main"
        self._render_menu()

    
    def _system_restart(self):
        """Handle system restart button click."""
        # Show confirmation dialog
        from tkinter import messagebox
        if messagebox.askyesno("System Restart", "Are you sure you want to restart the system?"):
            logging.info("System restart initiated by admin")
        
            # Clean up resources
            if hasattr(self, 'timeout_after') and self.timeout_after:
                self.root.after_cancel(self.timeout_after)
                self.timeout_after = None
        
            # Notify parent app to shut down
            if hasattr(self, "on_system_restart"):
                self.on_system_restart()
            else:
                # Fallback if callback not set
                try:
                    # Clean up GPIO
                    import RPi.GPIO as GPIO
                    GPIO.cleanup()
                
                    # Destroy root window
                    self.root.destroy()
                
                    # Exit program
                    import sys
                    sys.exit(0)
                except Exception as e:
                    logging.error(f"Error during system restart: {e}")

    
    def _on_activity(self, event=None):
        """Reset inactivity timer on any user activity."""
        # Reset inactivity timer
        self.last_activity_ts = time.time()

    def start(self):
        logging.info("Admin: Starting mode")
        
        # Hide the main label first
        self.label.place_forget()
        
        # Create a new login screen each time
        if self.login_screen:
            self.login_screen.hide()  # Hide any existing login screen
        
        # Create fresh login screen
        self.login_screen = AdminLoginScreen(self.root)
        self.login_screen.on_login_success = self._on_login_success
        self.login_screen.on_login_failed = self._on_login_failed
        self.login_screen.on_login_cancel = self._on_login_cancel
        
        # Show login screen
        self.login_screen.show()

    def stop(self):
        logging.info("Admin: Stopping mode")
        # Hide admin interface
        self.label.place_forget()
        
        # Hide login screen if it exists
        if self.login_screen:
            self.login_screen.hide()
        
        # Cancel timeout timer
        if self.timeout_after:
            self.root.after_cancel(self.timeout_after)
            self.timeout_after = None

    def _on_login_success(self):
        """Handle successful login to admin mode."""
        logging.info("Admin login successful")
        
        # Hide login screen
        self.login_screen.hide()
        
        # Reset activity timestamp
        self.last_activity_ts = time.time()
        
        # Reset to main menu
        self.current_menu = "main"
        
        # Show admin interface
        self.label.place(x=0, y=0, width=WINDOW_W, height=WINDOW_H)
        self.label.lift()

        # Load background image
        self.base_bg = self._load_bg()
        
        # Render the menu
        self._render_menu()
        
        # Start inactivity timer
        self._arm_timeout()

    def _on_login_failed(self):
        """Handle login failure."""
        logging.info("Admin login failed")
        if hasattr(self, "on_exit"):
            self.on_exit()
            
    def _on_login_cancel(self):
        """Handle login cancellation."""
        logging.info("Admin login cancelled")
        if hasattr(self, "on_exit"):
            self.on_exit()

    def _load_bg(self):
        """Load background image with better error handling."""
        try:
            if ADMIN_BG_PATH.exists():
                logging.info(f"Loading admin background from: {ADMIN_BG_PATH}")
                with Image.open(ADMIN_BG_PATH) as im:
                    if im.mode in ("RGBA", "P"):
                        im = im.convert("RGB")
                    return self._letterbox(im)
            else:
                logging.error(f"Admin background image not found: {ADMIN_BG_PATH}")
        except Exception as e:
            logging.error(f"Admin: Failed to load background: {e}")
            import traceback
            logging.error(traceback.format_exc())
        
        # Return a fallback white background
        logging.info("Using fallback white background for admin mode")
        return Image.new("RGB", (WINDOW_W, WINDOW_H), (255, 255, 255))

    def _letterbox(self, im: Image.Image):
        """Force letterboxing by scaling to fit screen."""
        iw, ih = im.size
        scale = min(WINDOW_W/iw, WINDOW_H/ih)
        nw, nh = int(iw*scale), int(ih*scale)
        resized = im.resize((nw, nh), Image.LANCZOS)
        bg = Image.new("RGB", (WINDOW_W, WINDOW_H), (255,255,255))
        bg.paste(resized, ((WINDOW_W-nw)//2, (WINDOW_H-nh)//2))
        return bg
        
    def _render_menu(self):
        """Render the main admin menu with safety checks."""
        print("DEBUG: Executing second _render_menu method (line 1813)")
        logging.info("DEBUG: Executing second _render_menu method (line 1813)")
        
        if not hasattr(self, 'base_bg') or self.base_bg is None:
            logging.error("Cannot render menu: base_bg is None")
            self.base_bg = Image.new("RGB", (WINDOW_W, WINDOW_H), (255, 255, 255))
        
        try:
            frame = self.base_bg.copy()
            d = ImageDraw.Draw(frame)
            
            # Menu options - with touch-friendly buttons
            option_font = load_ttf(40)  # Increased for 1280x1024
            
            # Main menu buttons
            buttons = [
                {"text": "Credentials", "y": 300, "color": (0,120,200)},
                {"text": "Wireless", "y": 400, "color": (0,150,100)},
                {"text": "System Settings", "y": 500, "color": (100,150,0)},  # Add this line
                {"text": "Exit Admin Mode", "y": 600, "color": (200,60,60)},  # Move down
                {"text": "System Restart", "y": 700, "color": (150,30,30)}    # Move down
            ]

            # Add logging to check buttons
            logging.info(f"Rendering admin menu with {len(buttons)} buttons")
            for i, btn in enumerate(buttons):
                logging.info(f"Button {i+1}: {btn['text']} at y={btn['y']}")
            
            for btn in buttons:
                button_x, button_y = 100, btn["y"]
                text_w, text_h = d.textbbox((0,0), btn["text"], font=option_font)[2:]
                
                # Draw button
                d.rectangle([button_x-20, button_y-10, button_x+text_w+40, button_y+text_h+10], 
                           fill=btn["color"], outline=(0,0,0), width=2)
                d.text((button_x, button_y), btn["text"], font=option_font, fill=(255,255,255))

            self.tk_img = ImageTk.PhotoImage(frame)
            self.label.configure(image=self.tk_img)
            self.label.lift()
            
            # Reset the back_to_menu flag
            if hasattr(self, 'back_to_menu'):
                delattr(self, 'back_to_menu')
                
        except Exception as e:
            logging.error(f"Error rendering admin menu: {e}")
            import traceback
            logging.error(traceback.format_exc())



    def _render_credentials_menu(self):
        """Render the credentials submenu."""
        if not hasattr(self, 'base_bg') or self.base_bg is None:
            logging.error("Cannot render credentials menu: base_bg is None")
            self.base_bg = Image.new("RGB", (WINDOW_W, WINDOW_H), (255, 255, 255))
        
        try:
            frame = self.base_bg.copy()
            d = ImageDraw.Draw(frame)
            
            # Add title
            title_font = load_ttf(48)
            title_text = "Credentials Menu"
            tw, th = d.textbbox((0,0), title_text, font=title_font)[2:]
            d.text(((WINDOW_W - tw)//2, 100), title_text, font=title_font, fill=(0,0,0))
            
            # Menu options - with touch-friendly buttons
            option_font = load_ttf(40)
            
            # Credentials submenu buttons
            buttons = [
                {"text": "Update Credentials", "y": 300, "color": (0,120,200)},
                {"text": "Update Location Files", "y": 400, "color": (0,150,100)},
                {"text": "Back to Main Menu", "y": 500, "color": (100,100,200)}
            ]
            
            for btn in buttons:
                button_x, button_y = 100, btn["y"]
                text_w, text_h = d.textbbox((0,0), btn["text"], font=option_font)[2:]
                
                # Draw button
                d.rectangle([button_x-20, button_y-10, button_x+text_w+40, button_y+text_h+10], 
                           fill=btn["color"], outline=(0,0,0), width=2)
                d.text((button_x, button_y), btn["text"], font=option_font, fill=(255,255,255))

            self.tk_img = ImageTk.PhotoImage(frame)
            self.label.configure(image=self.tk_img)
            self.label.lift()
            
            # Reset the back_to_menu flag
            if hasattr(self, 'back_to_menu'):
                delattr(self, 'back_to_menu')
                
        except Exception as e:
            logging.error(f"Error rendering credentials menu: {e}")
            import traceback
            logging.error(traceback.format_exc())

    def _render_wireless_menu(self):
        """Render the wireless submenu."""
        if not hasattr(self, 'base_bg') or self.base_bg is None:
            logging.error("Cannot render wireless menu: base_bg is None")
            self.base_bg = Image.new("RGB", (WINDOW_W, WINDOW_H), (255, 255, 255))
        
        try:
            frame = self.base_bg.copy()
            d = ImageDraw.Draw(frame)
            
            # Add title
            title_font = load_ttf(48)
            title_text = "Wireless Menu"
            tw, th = d.textbbox((0,0), title_text, font=title_font)[2:]
            d.text(((WINDOW_W - tw)//2, 100), title_text, font=title_font, fill=(0,0,0))
            
            # Menu options - with touch-friendly buttons
            option_font = load_ttf(40)
            
            # Wireless submenu buttons
            buttons = [
                {"text": "WiFi Settings", "y": 300, "color": (0,120,200)},
                {"text": "Local IP", "y": 400, "color": (0,150,100)},
                {"text": "Bluetooth", "y": 500, "color": (100,100,200)},
                {"text": "Back to Main Menu", "y": 600, "color": (150,100,150)}
            ]
            
            for btn in buttons:
                button_x, button_y = 100, btn["y"]
                text_w, text_h = d.textbbox((0,0), btn["text"], font=option_font)[2:]
                
                # Draw button
                d.rectangle([button_x-20, button_y-10, button_x+text_w+40, button_y+text_h+10], 
                           fill=btn["color"], outline=(0,0,0), width=2)
                d.text((button_x, button_y), btn["text"], font=option_font, fill=(255,255,255))

            self.tk_img = ImageTk.PhotoImage(frame)
            self.label.configure(image=self.tk_img)
            self.label.lift()
            
            # Reset the back_to_menu flag
            if hasattr(self, 'back_to_menu'):
                delattr(self, 'back_to_menu')
                
        except Exception as e:
            logging.error(f"Error rendering wireless menu: {e}")
            import traceback
            logging.error(traceback.format_exc())


    def _render_status(self, message, is_error=False):
        """Render status message with safety checks."""
        if self.base_bg is None:
            logging.error("Cannot render status: base_bg is None")
            # Create a fallback background
            self.base_bg = Image.new("RGB", (WINDOW_W, WINDOW_H), (255, 255, 255))
            
        frame = self.base_bg.copy()
        d = ImageDraw.Draw(frame)
        
        # Status message
        status_font = load_ttf(36)  # Increased for 1280x1024
        color = (255,0,0) if is_error else (0,128,0)
        sw, sh = d.textbbox((0,0), message, font=status_font)[2:]
        d.text(((WINDOW_W - sw)//2, 250), message, font=status_font, fill=color)

        # Back to Menu button
        button_x, button_y = 100, 500
        button_text = "Back to Menu"
        bw, bh = d.textbbox((0,0), button_text, font=status_font)[2:]
        d.rectangle([button_x-20, button_y-10, button_x+bw+40, button_y+bh+10], 
                   fill=(0,120,200), outline=(0,0,0), width=2)
        d.text((button_x, button_y), button_text, font=status_font, fill=(255,255,255))

        self.tk_img = ImageTk.PhotoImage(frame)
        self.label.configure(image=self.tk_img)
        self.label.lift()
        
        # Set flag to indicate we're in a status screen
        self.back_to_menu = True

    def _arm_timeout(self):
        """Set up inactivity timeout for admin mode."""
        if self.timeout_after:
            self.root.after_cancel(self.timeout_after)
            
        def check_timeout():
            current_time = time.time()
            elapsed = current_time - self.last_activity_ts
            logging.debug(f"Admin timeout check: {elapsed:.1f}s elapsed")
            
            # Changed from 90 seconds to 5 minutes (300 seconds)
            if elapsed >= 300.0:
                logging.info(f"Admin mode timeout after {elapsed:.1f}s - returning to Idle")
                if hasattr(self, "on_timeout"):
                    self.on_timeout()
                return
            self.timeout_after = self.root.after(1000, check_timeout)
            
        self.timeout_after = self.root.after(1000, check_timeout)

    def show_local_ip(self):
        """Show the local IP address."""
        if self.update_in_progress:
            return
            
        self.update_in_progress = True
        
        try:
            # Get IP addresses
            ip_info = self._get_ip_addresses()
            
            # Create popup frame
            ip_frame = tk.Frame(self.root, bg="#2c3e50")
            ip_frame.place(x=0, y=0, width=WINDOW_W, height=WINDOW_H)
            
            # Title
            title_label = tk.Label(ip_frame, text="Network Information", 
                                  font=("Arial", 36, "bold"), bg="#2c3e50", fg="white")
            title_label.pack(pady=(50, 30))
            
            # IP information
            info_frame = tk.Frame(ip_frame, bg="#2c3e50")
            info_frame.pack(pady=20, fill=tk.BOTH, expand=True)
            
            # Create a canvas with scrollbar for IP info
            canvas = tk.Canvas(info_frame, bg="#2c3e50", highlightthickness=0)
            scrollbar = tk.Scrollbar(info_frame, orient="vertical", command=canvas.yview)
            scrollable_frame = tk.Frame(canvas, bg="#2c3e50")
            
            scrollable_frame.bind(
                "<Configure>",
                lambda e: canvas.configure(
                    scrollregion=canvas.bbox("all")
                )
            )
            
            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)
            
            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")
            
            # Add IP information to scrollable frame
            for interface, addresses in ip_info.items():
                # Interface header
                interface_label = tk.Label(scrollable_frame, text=f"Interface: {interface}", 
                                         font=("Arial", 18, "bold"), bg="#2c3e50", fg="white")
                interface_label.pack(anchor="w", padx=50, pady=(10, 5))
                
                # IP addresses
                for addr_type, addr in addresses.items():
                    addr_label = tk.Label(scrollable_frame, text=f"{addr_type}: {addr}", 
                                        font=("Arial", 16), bg="#2c3e50", fg="white")
                    addr_label.pack(anchor="w", padx=70, pady=2)
            
            # Back button
            back_button = tk.Button(ip_frame, text="Back", font=("Arial", 18),
                                   bg="#e74c3c", fg="white", width=10,
                                   command=lambda: self._close_ip_info(ip_frame))
            back_button.pack(pady=30)
            
        except Exception as e:
            logging.error(f"Failed to show IP information: {e}")
            self._render_status(f"Error showing IP information: {str(e)}", is_error=True)
            
        finally:
            self.update_in_progress = False
    
    def _get_ip_addresses(self):
        """Get IP addresses for all network interfaces."""
        ip_info = {}
        
        try:
            # Get all interfaces
            interfaces = subprocess.check_output("ls /sys/class/net", shell=True).decode().strip().split()
            
            for interface in interfaces:
                # Skip loopback interface
                if interface == "lo":
                    continue
                    
                ip_info[interface] = {}
                
                # Get IPv4 address
                try:
                    ipv4 = subprocess.check_output(f"ip -4 addr show {interface} | grep -oP '(?<=inet\\s)\\d+(\\.\\d+){{3}}'", shell=True).decode().strip()
                    if ipv4:
                        ip_info[interface]["IPv4"] = ipv4
                except:
                    ip_info[interface]["IPv4"] = "Not available"
                
                # Get IPv6 address
                try:
                    ipv6 = subprocess.check_output(f"ip -6 addr show {interface} | grep -oP '(?<=inet6\\s)[0-9a-f:]+' | head -n 1", shell=True).decode().strip()
                    if ipv6:
                        ip_info[interface]["IPv6"] = ipv6
                except:
                    ip_info[interface]["IPv6"] = "Not available"
                
                # Get MAC address
                try:
                    mac = subprocess.check_output(f"cat /sys/class/net/{interface}/address", shell=True).decode().strip()
                    if mac:
                        ip_info[interface]["MAC"] = mac
                except:
                    ip_info[interface]["MAC"] = "Not available"
                
                # Get link status
                try:
                    status = subprocess.check_output(f"cat /sys/class/net/{interface}/operstate", shell=True).decode().strip()
                    ip_info[interface]["Status"] = status
                except:
                    ip_info[interface]["Status"] = "Unknown"
                
                # For WiFi interfaces, get SSID
                if interface.startswith("wl"):
                    try:
                        ssid = subprocess.check_output(f"iwgetid {interface} -r", shell=True).decode().strip()
                        if ssid:
                            ip_info[interface]["SSID"] = ssid
                    except:
                        pass
        
        except Exception as e:
            logging.error(f"Error getting IP addresses: {e}")
            ip_info["Error"] = {"Message": str(e)}
        
        return ip_info
    
    def _close_ip_info(self, ip_frame):
        """Close IP information popup."""
        ip_frame.destroy()
        self._render_wireless_menu()
    
    def open_bluetooth_settings(self):
        """Open Bluetooth settings."""
        if self.update_in_progress:
            return
            
        self.update_in_progress = True
        
        try:
            # Create Bluetooth settings frame
            bt_frame = tk.Frame(self.root, bg="#2c3e50")
            bt_frame.place(x=0, y=0, width=WINDOW_W, height=WINDOW_H)
            
            # Title
            title_label = tk.Label(bt_frame, text="Bluetooth Settings", 
                                  font=("Arial", 36, "bold"), bg="#2c3e50", fg="white")
            title_label.pack(pady=(30, 20))
            
            # Main content frame with two columns
            content_frame = tk.Frame(bt_frame, bg="#2c3e50")
            content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
            content_frame.columnconfigure(0, weight=1)
            content_frame.columnconfigure(1, weight=1)
            
            # Left column - Available devices
            left_frame = tk.Frame(content_frame, bg="#2c3e50", bd=2, relief=tk.GROOVE)
            left_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
            
            available_label = tk.Label(left_frame, text="Available Devices", 
                                     font=("Arial", 18, "bold"), bg="#2c3e50", fg="white")
            available_label.pack(pady=10)
            
            # Listbox for available devices
            available_frame = tk.Frame(left_frame, bg="#2c3e50")
            available_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            available_listbox = tk.Listbox(available_frame, font=("Arial", 14), height=10)
            available_scrollbar = tk.Scrollbar(available_frame, orient=tk.VERTICAL)
            available_listbox.config(yscrollcommand=available_scrollbar.set)
            available_scrollbar.config(command=available_listbox.yview)
            
            available_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            available_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            # Buttons for available devices
            available_buttons = tk.Frame(left_frame, bg="#2c3e50")
            available_buttons.pack(fill=tk.X, pady=10)
            
            scan_button = tk.Button(available_buttons, text="Scan", font=("Arial", 14),
                                  bg="#3498db", fg="white", width=10,
                                  command=lambda: self._scan_bluetooth(available_listbox))
            scan_button.pack(side=tk.LEFT, padx=5, expand=True)
            
            pair_button = tk.Button(available_buttons, text="Pair", font=("Arial", 14),
                                  bg="#2ecc71", fg="white", width=10,
                                  command=lambda: self._pair_bluetooth(available_listbox))
            pair_button.pack(side=tk.LEFT, padx=5, expand=True)
            
            # Right column - Paired devices
            right_frame = tk.Frame(content_frame, bg="#2c3e50", bd=2, relief=tk.GROOVE)
            right_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
            
            paired_label = tk.Label(right_frame, text="Paired Devices", 
                                  font=("Arial", 18, "bold"), bg="#2c3e50", fg="white")
            paired_label.pack(pady=10)
            
            # Listbox for paired devices
            paired_frame = tk.Frame(right_frame, bg="#2c3e50")
            paired_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            paired_listbox = tk.Listbox(paired_frame, font=("Arial", 14), height=10)
            paired_scrollbar = tk.Scrollbar(paired_frame, orient=tk.VERTICAL)
            paired_listbox.config(yscrollcommand=paired_scrollbar.set)
            paired_scrollbar.config(command=paired_listbox.yview)
            
            paired_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            paired_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            # Buttons for paired devices
            paired_buttons = tk.Frame(right_frame, bg="#2c3e50")
            paired_buttons.pack(fill=tk.X, pady=10)
            
            refresh_button = tk.Button(paired_buttons, text="Refresh", font=("Arial", 14),
                                     bg="#3498db", fg="white", width=10,
                                     command=lambda: self._refresh_paired_devices(paired_listbox))
            refresh_button.pack(side=tk.LEFT, padx=5, expand=True)
            
            forget_button = tk.Button(paired_buttons, text="Forget", font=("Arial", 14),
                                    bg="#e74c3c", fg="white", width=10,
                                    command=lambda: self._forget_bluetooth(paired_listbox))
            forget_button.pack(side=tk.LEFT, padx=5, expand=True)
            
            # Status area
            status_frame = tk.Frame(bt_frame, bg="#2c3e50", height=100)
            status_frame.pack(fill=tk.X, pady=10)
            
            self.bt_status_label = tk.Label(status_frame, text="Ready", 
                                          font=("Arial", 14), bg="#2c3e50", fg="white")
            self.bt_status_label.pack(pady=10)
            
            # Back button
            back_button = tk.Button(bt_frame, text="Back", font=("Arial", 18),
                                   bg="#e74c3c", fg="white", width=10,
                                   command=lambda: self._close_bluetooth_settings(bt_frame))
            back_button.pack(pady=20)
            
            # Initial population of lists
            self._scan_bluetooth(available_listbox)
            self._refresh_paired_devices(paired_listbox)
            
        except Exception as e:
            logging.error(f"Failed to open Bluetooth settings: {e}")
            self._render_status(f"Error opening Bluetooth settings: {str(e)}", is_error=True)
            
        finally:
            self.update_in_progress = False
    
    def _scan_bluetooth(self, listbox):
        """Scan for available Bluetooth devices."""
        try:
            # Clear listbox
            listbox.delete(0, tk.END)
            
            # Update status
            if hasattr(self, 'bt_status_label'):
                self.bt_status_label.config(text="Scanning for devices...")
            
            # Put Bluetooth adapter in discoverable mode
            subprocess.run("sudo hciconfig hci0 piscan", shell=True)
            
            # Scan for devices
            output = subprocess.check_output("sudo timeout 10s hcitool scan", shell=True).decode()
            
            # Parse output
            devices = []
            for line in output.splitlines():
                if "Scanning" in line:
                    continue
                parts = line.strip().split("\t")
                if len(parts) >= 2:
                    addr = parts[0].strip()
                    name = parts[1].strip() if len(parts) > 1 else "Unknown"
                    devices.append((addr, name))
            
            # Add to listbox
            for addr, name in devices:
                listbox.insert(tk.END, f"{name} ({addr})")
            
            # Update status
            if hasattr(self, 'bt_status_label'):
                self.bt_status_label.config(text=f"Found {len(devices)} devices")
            
        except Exception as e:
            logging.error(f"Error scanning for Bluetooth devices: {e}")
            if hasattr(self, 'bt_status_label'):
                self.bt_status_label.config(text=f"Error: {str(e)}")
    
    def _refresh_paired_devices(self, listbox):
        """Refresh list of paired Bluetooth devices."""
        try:
            # Clear listbox
            listbox.delete(0, tk.END)
            
            # Update status
            if hasattr(self, 'bt_status_label'):
                self.bt_status_label.config(text="Getting paired devices...")
            
            # Get paired devices
            output = subprocess.check_output("bluetoothctl paired-devices", shell=True).decode()
            
            # Parse output
            devices = []
            for line in output.splitlines():
                parts = line.strip().split(" ", 2)
                if len(parts) >= 3:
                    addr = parts[1].strip()
                    name = parts[2].strip()
                    devices.append((addr, name))
            
            # Add to listbox
            for addr, name in devices:
                listbox.insert(tk.END, f"{name} ({addr})")
            
            # Update status
            if hasattr(self, 'bt_status_label'):
                self.bt_status_label.config(text=f"Found {len(devices)} paired devices")
            
        except Exception as e:
            logging.error(f"Error getting paired Bluetooth devices: {e}")
            if hasattr(self, 'bt_status_label'):
                self.bt_status_label.config(text=f"Error: {str(e)}")
    
    def _pair_bluetooth(self, listbox):
        """Pair with selected Bluetooth device."""
        try:
            # Get selected device
            selection = listbox.curselection()
            if not selection:
                if hasattr(self, 'bt_status_label'):
                    self.bt_status_label.config(text="No device selected")
                return
            
            device_text = listbox.get(selection[0])
            
            # Extract address
            import re
            match = re.search(r'\((.*?)\)', device_text)
            if not match:
                if hasattr(self, 'bt_status_label'):
                    self.bt_status_label.config(text="Invalid device format")
                return
            
            addr = match.group(1)
            
            # Update status
            if hasattr(self, 'bt_status_label'):
                self.bt_status_label.config(text=f"Pairing with {addr}...")
            
            # Pair with device
            # Note: This is a simplified approach. Real pairing might require PIN confirmation
            subprocess.run(f"echo 'pair {addr}' | bluetoothctl", shell=True)
            
            # Update status
            if hasattr(self, 'bt_status_label'):
                self.bt_status_label.config(text=f"Paired with {addr}")
            
            # Refresh paired devices list
            self._refresh_paired_devices(listbox)
            
        except Exception as e:
            logging.error(f"Error pairing Bluetooth device: {e}")
            if hasattr(self, 'bt_status_label'):
                self.bt_status_label.config(text=f"Error: {str(e)}")
    
    def _forget_bluetooth(self, listbox):
        """Forget selected paired Bluetooth device."""
        try:
            # Get selected device
            selection = listbox.curselection()
            if not selection:
                if hasattr(self, 'bt_status_label'):
                    self.bt_status_label.config(text="No device selected")
                return
            
            device_text = listbox.get(selection[0])
            
            # Extract address
            import re
            match = re.search(r'\((.*?)\)', device_text)
            if not match:
                if hasattr(self, 'bt_status_label'):
                    self.bt_status_label.config(text="Invalid device format")
                return
            
            addr = match.group(1)
            
            # Update status
            if hasattr(self, 'bt_status_label'):
                self.bt_status_label.config(text=f"Removing {addr}...")
            
            # Remove device
            subprocess.run(f"echo 'remove {addr}' | bluetoothctl", shell=True)
            
            # Update status
            if hasattr(self, 'bt_status_label'):
                self.bt_status_label.config(text=f"Removed {addr}")
            
            # Refresh paired devices list
            self._refresh_paired_devices(listbox)
            
        except Exception as e:
            logging.error(f"Error removing Bluetooth device: {e}")
            if hasattr(self, 'bt_status_label'):
                self.bt_status_label.config(text=f"Error: {str(e)}")
    
    def _close_bluetooth_settings(self, bt_frame):
        """Close Bluetooth settings."""
        bt_frame.destroy()
        self._render_wireless_menu()

def _system_restart(self):
    """Handle system restart button click."""
    # Show confirmation dialog
    from tkinter import messagebox
    if messagebox.askyesno("System Restart", "Are you sure you want to restart the system?"):
        logging.info("System restart initiated by admin")
        
        # Clean up resources
        if hasattr(self, 'timeout_after') and self.timeout_after:
            self.root.after_cancel(self.timeout_after)
            self.timeout_after = None
        
        # Notify parent app to shut down
        if hasattr(self, "on_system_restart"):
            self.on_system_restart()
        else:
            # Fallback if callback not set
            try:
                # Clean up GPIO
                import RPi.GPIO as GPIO
                GPIO.cleanup()
                
                # Destroy root window
                self.root.destroy()
                
                # Exit program
                import sys
                sys.exit(0)
            except Exception as e:
                logging.error(f"Error during system restart: {e}")

    

    def update_credentials(self):
        """Update credential files from Google Sheet."""
        if self.update_in_progress:
            return

        self.update_in_progress = True
        self._render_status("Updating credentials...")

        try:
            # Connect to Google Sheet
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/spreadsheets",
            ]
            creds = Credentials.from_service_account_file(str(GS_CRED_PATH), scopes=scopes)
            gc = gspread.authorize(creds)

            # Open sheet and get credentials tab
            sheet = gc.open(GS_SHEET_NAME).worksheet(GS_CRED_TAB)

            # Create credentials directory if it doesn't exist
            CRED_DIR.mkdir(parents=True, exist_ok=True)

            # Update Cloudflared_Host from cell B18
            cloudflared_host = sheet.acell('B18').value
            with open(CRED_DIR / "Cloudflared_Host", 'w') as f:
                f.write(cloudflared_host or "")

            # Update GoogleFolderID.txt from cell B13
            folder_id = sheet.acell('B13').value
            with open(CRED_DIR / "GoogleFolderID.txt", 'w') as f:
                f.write(folder_id or "")

            # Update MachineID.txt from cell B25
            machine_id = sheet.acell('B25').value
            with open(CRED_DIR / "MachineID.txt", 'w') as f:
                f.write(machine_id or "")

            # Update GoogleCredEmail.txt from cell B12
            cred_email = sheet.acell('B12').value
            with open(CRED_DIR / "GoogleCredEmail.txt", 'w') as f:
                f.write(cred_email or "")

            logging.info("Admin: Successfully updated credential files")
            self._render_status("Credentials updated successfully!")

        except Exception as e:
            logging.error("Admin: Failed to update credentials: %s", e)
            self._render_status(f"Error: {str(e)}", is_error=True)

        finally:
            self.update_in_progress = False
            
    def update_location_files(self):
        """Update location-related files (weather, UPC catalog, hours)."""
        if self.update_in_progress:
            return
            
        self.update_in_progress = True
        self._render_status("Updating location files...")
        
        try:
            # Connect to Google Sheet
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/spreadsheets",
            ]
            creds = Credentials.from_service_account_file(str(GS_CRED_PATH), scopes=scopes)
            gc = gspread.authorize(creds)
            
            # Open sheet
            sheet = gc.open(GS_SHEET_NAME)
            
            # 1. Update weather zipcode
            cred_tab = sheet.worksheet(GS_CRED_TAB)
            zipcode = cred_tab.acell('B29').value
            weather_api_key = cred_tab.acell('B33').value
            
            # Save zipcode and API key
            with open(CRED_DIR / "WeatherZipcode.txt", 'w') as f:
                f.write(zipcode or "")
            with open(CRED_DIR / "WeatherAPIKey.txt", 'w') as f:
                f.write(weather_api_key or "")
                
            # 2. Download UPC catalog
            try:
                inv_tab = sheet.worksheet(GS_TAB)
                rows = inv_tab.get_all_values()
                
                # Save as CSV
                with open(CRED_DIR / "upc_catalog.csv", 'w', newline='') as f:
                    import csv
                    writer = csv.writer(f)
                    writer.writerows(rows)
                logging.info(f"Saved UPC catalog with {len(rows)} rows")
            except Exception as e:
                logging.error(f"Failed to download UPC catalog: {e}")
                
            # 3. Download schedule from Hours tab
            try:
                hours_tab = sheet.worksheet("Hours")
                hours_data = hours_tab.get_all_values()
                
                # Save as CSV
                with open(CRED_DIR / "store_hours.csv", 'w', newline='') as f:
                    import csv
                    writer = csv.writer(f)
                    writer.writerows(hours_data)
                logging.info(f"Saved store hours with {len(hours_data)} rows")
            except Exception as e:
                logging.error(f"Failed to download store hours: {e}")
            
            self._render_status("Location files updated successfully!")
            
        except Exception as e:
            logging.error(f"Failed to update location files: {e}")
            self._render_status(f"Error: {str(e)}", is_error=True)
            
        finally:
            self.update_in_progress = False
    
    def open_wifi_settings(self):
        """Open WiFi settings with virtual keyboard."""
        if self.update_in_progress:
            return
            
        self.update_in_progress = True
        
        try:
            # Create WiFi settings frame
            wifi_frame = tk.Frame(self.root, bg="#2c3e50")
            wifi_frame.place(x=0, y=0, width=WINDOW_W, height=WINDOW_H)
            
            # Title
            title_label = tk.Label(wifi_frame, text="WiFi Settings", 
                                  font=("Arial", 36, "bold"), bg="#2c3e50", fg="white")
            title_label.pack(pady=(50, 30))
            
            # Network selection
            networks_frame = tk.Frame(wifi_frame, bg="#2c3e50")
            networks_frame.pack(pady=20, fill=tk.X)
            
            networks_label = tk.Label(networks_frame, text="Available Networks:", 
                                     font=("Arial", 24), bg="#2c3e50", fg="white")
            networks_label.pack(anchor=tk.W, padx=50)
            
            # Get available networks
            networks = self._get_wifi_networks()
            
            # Network listbox
            network_listbox = tk.Listbox(networks_frame, font=("Arial", 18), height=6, width=40)
            network_listbox.pack(padx=50, pady=10, fill=tk.X)
            
            # Populate networks
            for network in networks:
                network_listbox.insert(tk.END, network)
            
            # Password entry
            password_frame = tk.Frame(wifi_frame, bg="#2c3e50")
            password_frame.pack(pady=20, fill=tk.X)
            
            password_label = tk.Label(password_frame, text="Password:", 
                                     font=("Arial", 24), bg="#2c3e50", fg="white")
            password_label.pack(anchor=tk.W, padx=50)
            
            password_var = tk.StringVar()
            password_entry = tk.Entry(password_frame, textvariable=password_var,
                                     font=("Arial", 18), width=30, show="*")
            password_entry.pack(padx=50, pady=10, fill=tk.X)
            
            # Buttons
            button_frame = tk.Frame(wifi_frame, bg="#2c3e50")
            button_frame.pack(pady=30)
            
            connect_button = tk.Button(button_frame, text="Connect", font=("Arial", 18),
                                     bg="#27ae60", fg="white", width=10,
                                     command=lambda: self._connect_wifi(network_listbox.get(tk.ACTIVE), password_var.get()))
            connect_button.pack(side=tk.LEFT, padx=20)
            
            back_button = tk.Button(button_frame, text="Back", font=("Arial", 18),
                                   bg="#e74c3c", fg="white", width=10,
                                   command=lambda: self._close_wifi_settings(wifi_frame))
            back_button.pack(side=tk.LEFT, padx=20)
            
            # Create virtual keyboard
            keyboard_frame = tk.Frame(wifi_frame, bg="#34495e")
            keyboard_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=20)
            
            # Define keyboard layout
            keys = [
                ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
                ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
                ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l'],
                ['z', 'x', 'c', 'v', 'b', 'n', 'm', '.', '@']
            ]
            
            # Create keyboard buttons
            for row_idx, row in enumerate(keys):
                row_frame = tk.Frame(keyboard_frame, bg="#34495e")
                row_frame.pack(fill=tk.X, pady=2)
                
                for key in row:
                    btn = tk.Button(row_frame, text=key, font=("Arial", 16),
                                  width=3, height=1, bg="#7f8c8d", fg="white", 
                                  command=lambda k=key: self._key_press(password_entry, k))
                    btn.pack(side=tk.LEFT, padx=2)
            
            # Special keys row
            special_frame = tk.Frame(keyboard_frame, bg="#34495e")
            special_frame.pack(fill=tk.X, pady=2)
            
            # Space key
            space_btn = tk.Button(special_frame, text="Space", font=("Arial", 16), 
                                width=20, height=1, bg="#7f8c8d", fg="white",
                                command=lambda: self._key_press(password_entry, " "))
            space_btn.pack(side=tk.LEFT, padx=2)
            
            # Backspace key
            backspace_btn = tk.Button(special_frame, text="Backspace", font=("Arial", 16), 
                                    width=10, height=1, bg="#e67e22", fg="white",
                                    command=lambda: self._backspace(password_entry))
            backspace_btn.pack(side=tk.LEFT, padx=2)
            
            # Focus password entry
            password_entry.focus_set()
            
        except Exception as e:
            logging.error(f"Failed to open WiFi settings: {e}")
            self._render_status(f"Error opening WiFi settings: {str(e)}", is_error=True)
            
        finally:
            self.update_in_progress = False
    
    def _get_wifi_networks(self):
        """Get list of available WiFi networks."""
        try:
            # Use iwlist to scan for networks
            output = subprocess.check_output("sudo iwlist wlan0 scan | grep ESSID", shell=True)
            networks = []
            for line in output.decode('utf-8').splitlines():
                if 'ESSID:' in line:
                    network = line.split('ESSID:"')[1].split('"')[0]
                    if network and network not in networks:
                        networks.append(network)
            return networks
        except Exception as e:
            logging.error(f"Failed to get WiFi networks: {e}")
            return ["WiFi 1", "WiFi 2", "WiFi 3"]  # Fallback for testing
    
    def _connect_wifi(self, network, password):
        """Connect to WiFi network."""
        if not network:
            return
            
        try:
            # Create wpa_supplicant entry
            config = f'''
network={{
    ssid="{network}"
    psk="{password}"
}}
'''
            # Write to temporary file
            with open("/tmp/wpa_supplicant.conf", "w") as f:
                f.write(config)
                
            # Apply configuration
            subprocess.run("sudo cp /tmp/wpa_supplicant.conf /etc/wpa_supplicant/wpa_supplicant.conf", shell=True)
            subprocess.run("sudo wpa_cli -i wlan0 reconfigure", shell=True)
            
            # Show status
            self._render_status(f"Connected to {network}")
            
        except Exception as e:
            logging.error(f"Failed to connect to WiFi: {e}")
            self._render_status(f"Error connecting to WiFi: {str(e)}", is_error=True)
    
    def _close_wifi_settings(self, wifi_frame):
        """Close WiFi settings and return to wireless menu."""
        wifi_frame.destroy()
        self._render_wireless_menu()
    
    def _key_press(self, entry, key):
        """Handle key press on virtual keyboard."""
        current_text = entry.get()
        entry.delete(0, tk.END)
        entry.insert(0, current_text + key)
        
    def _backspace(self, entry):
        """Handle backspace on virtual keyboard."""
        current_text = entry.get()
        if current_text:
            entry.delete(0, tk.END)
            entry.insert(0, current_text[:-1])
            
    def _clear_field(self, entry):
        """Handle clear on virtual keyboard."""
        entry.delete(0, tk.END)



# ==============================
#          Cart Mode
# ==============================
class CartMode:
    """
    Shopping cart mode for adding and managing items.
    Displays Cart.png as background with receipt recorder and totals.
    """
    def __init__(self, root, **kwargs):
        """Initialize the CartMode."""
        self.root = root
        self.label = tk.Label(root, bg="black")
        
        # Define cache directory
        self.cache_dir = Path.home() / "SelfCheck" / "Cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Get drive service directly from root if available
        self.drive_service = getattr(root, 'drive_service', None)
        
        # Log drive service status
        if self.drive_service:
            logging.info("Drive service successfully accessed in CartMode")
        else:
            logging.warning("Drive service not found in CartMode initialization")
        
        # Cart data structures
        self.cart_items = {}  # UPC -> {data, qty}
        self.upc_catalog = {}  # UPC -> row data
        self.transaction_id = self._generate_transaction_id()
        self.current_payment_method = None
        
        # UI elements
        self.tk_img = None
        self.base_bg = None
        self.receipt_frame = None
        self.receipt_canvas = None
        self.receipt_scrollbar = None
        self.receipt_items_frame = None
        self.totals_frame = None
        self.item_frames = []
        self.popup_frame = None
        self.manual_entry_frame = None
        
        # Config data
        self.business_name = "Vend Las Vegas"
        self.location = "1234 Fake Street\nTest NV\n89921"
        self.machine_id = "Prototype1001"
        self.tax_rate = 0.0  # Will be loaded from Tax.json
        
        # Timeout handling
        self.last_activity_ts = time.time()
        self.timeout_after = None
        self.timeout_popup = None
        self.countdown_label = None
        self.countdown_after = None
        self.countdown_value = 30
        
        # Add touch support
        self.label.bind("<Button-1>", self._on_touch)
        self.label.bind("<Motion>", self._on_activity)
        
        # Barcode input handling
        self.barcode_buffer = ""
        self.root.bind("<Key>", self._on_key)
        
        # Load UPC catalog and config files
        self._load_upc_catalog()
        self._load_config_files()
        
        # Test Google Sheets access
        self.sheets_access_ok = self.test_sheet_access()
        if self.sheets_access_ok:
            logging.info("Google Sheets access test passed")
        else:
            logging.warning("Google Sheets access test failed - logging to Service tab may not work")
            # Check permissions to help diagnose the issue
            self.check_spreadsheet_permissions()

    def _init_security_camera(self):
        """Initialize the security camera if enabled in settings."""
        # Check if OpenCV is available
        if not SecurityCamera.is_available():
            logging.error("OpenCV not available, security camera disabled")
            self.camera_enabled = False
            return
            
        # Check if camera is enabled in settings
        settings_path = Path.home() / "SelfCheck" / "Cred" / "Settings.json"
        try:
            with open(settings_path, 'r') as f:
                settings = json.load(f)
                camera_enabled = settings.get("camera_options", {}).get("security_camera_enabled", True)
        except Exception as e:
            logging.error(f"Error loading camera settings: {e}")
            camera_enabled = True  # Default to enabled if settings can't be loaded
        
        self.camera_enabled = camera_enabled
        
        if not self.camera_enabled:
            logging.info("Security camera disabled in settings")
            return
        
        # Initialize camera
        self.security_camera = SecurityCamera()
        self.camera_display_active = False
        self.camera_update_after = None
        self.recording_end_timer = None
        
        # Create videos directory
        self.videos_dir = Path.home() / "SelfCheck" / "TransactionVideos"
        self.videos_dir.mkdir(parents=True, exist_ok=True)


    def _create_camera_display(self):
        """Create the security camera display area."""
        if not hasattr(self, 'security_camera') or not self.camera_enabled:
            return
        
        # Create a frame for the camera display
        camera_width = 200  # Width of the camera display
        
        self.camera_frame = tk.LabelFrame(self.root, text="Security Camera", 
                                        font=("Arial", 14, "bold"), fg="white", bg="#34495e",
                                        bd=2, relief=tk.RAISED)
        
        # Position to the right of the buttons - adjust as needed for your layout
        # This positions it above the "Pay Now" button
        self.camera_frame.place(x=WINDOW_W//2 + 100, y=WINDOW_H-300, 
                              width=camera_width, height=150)
        
        # Camera display label
        self.camera_label = tk.Label(self.camera_frame, text="Initializing Camera...", 
                                   bg="black", fg="white", font=("Arial", 10))
        self.camera_label.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Start the camera
        if self.security_camera.start():
            self.camera_display_active = True
            self._update_camera_display()
            
            # Start recording
            self._start_transaction_recording()
        else:
            self.camera_label.config(text="Camera not available")

    def _update_camera_display(self):
        """Update the security camera display."""
        if not hasattr(self, 'camera_display_active') or not self.camera_display_active:
            return
        
        if not hasattr(self, 'security_camera'):
            return
            
        pil_image = self.security_camera.get_current_frame()
        
        if pil_image:
            try:
                # Scale up the image to fit the display area
                display_width = 180  # Adjust for padding
                display_height = 130
                
                # Resize with NEAREST filter for speed
                pil_image = pil_image.resize((display_width, display_height), Image.NEAREST)
                
                # Convert to PhotoImage
                photo = ImageTk.PhotoImage(pil_image)
                
                # Update label
                self.camera_label.config(image=photo, text="")
                self.camera_label.image = photo  # Keep a reference
                
            except Exception as e:
                logging.error(f"Camera display update error: {e}")
                self.camera_label.config(text=f"Camera Error")
        
        # Schedule next update
        if hasattr(self, 'camera_display_active') and self.camera_display_active:
            self.camera_update_after = self.root.after(100, self._update_camera_display)  # ~10 FPS

    def _start_transaction_recording(self):
        """Start recording video for this transaction."""
        if not hasattr(self, 'security_camera') or not self.camera_enabled:
            return
        
        # Create filename with transaction ID and timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = str(self.videos_dir / f"transaction_{self.transaction_id}_{timestamp}.avi")
        
        # Start recording
        if self.security_camera.start_recording(filename):
            logging.info(f"Started transaction recording: {filename}")
        else:
            logging.error("Failed to start transaction recording")

    def _schedule_recording_end(self):
        """Schedule the recording to end 10 seconds after thank you screen."""
        if not hasattr(self, 'security_camera') or not self.camera_enabled:
            return
            
        # Cancel any existing timer
        if hasattr(self, 'recording_end_timer') and self.recording_end_timer:
            self.root.after_cancel(self.recording_end_timer)
            
        # Schedule recording to end in 10 seconds
        self.recording_end_timer = self.root.after(10000, self._stop_transaction_recording)
        logging.info("Scheduled recording to end in 10 seconds")

    def _stop_transaction_recording(self):
        """Stop recording video."""
        if not hasattr(self, 'security_camera') or not self.camera_enabled:
            return
            
        if self.security_camera.stop_recording():
            logging.info("Stopped transaction recording")
        else:
            logging.warning("No active recording to stop")
    

    def start(self):
        """Start the Cart mode."""
        logging.info("CartMode: Starting")
        
        # Generate a new transaction ID
        self.transaction_id = self._generate_transaction_id()
        
        # Clear any existing cart data
        self.cart_items = {}
        
        # Clear barcode buffer
        self.barcode_buffer = ""
        
        # Reload tax rate from Tax.json to ensure it's current
        self._reload_tax_rate()
        
        # Create fresh UI
        self._create_ui()
        
        # Initialize and start security camera
        self._init_security_camera()
        if hasattr(self, 'camera_enabled') and self.camera_enabled:
            self._create_camera_display()
        
        # Start timeout timer
        self._arm_timeout()


    def stop(self):
        """Stop the Cart mode and clean up resources."""
        logging.info("CartMode: Stopping")
        
        # Stop camera
        if hasattr(self, 'security_camera'):
            self.camera_display_active = False
            if hasattr(self, 'camera_update_after') and self.camera_update_after:
                self.root.after_cancel(self.camera_update_after)
                self.camera_update_after = None
            if hasattr(self, 'recording_end_timer') and self.recording_end_timer:
                self.root.after_cancel(self.recording_end_timer)
                self.recording_end_timer = None
            self.security_camera.stop()
        
        # Cancel timers
        if self.timeout_after:
            self.root.after_cancel(self.timeout_after)
            self.timeout_after = None
            
        if self.countdown_after:
            self.root.after_cancel(self.countdown_after)
            self.countdown_after = None
        
        # Clean up Stripe webhook server if it exists
        if hasattr(self, 'stripe_webhook_thread') and self.stripe_webhook_thread:
            # The thread is daemon, so it will terminate when the main thread exits
            self.stripe_webhook_thread = None
            
        # Hide all UI elements
        if hasattr(self, 'label'):
            self.label.place_forget()
            
        if hasattr(self, 'receipt_frame'):
            self.receipt_frame.place_forget()
            
        if hasattr(self, 'totals_frame'):
            self.totals_frame.place_forget()
            
        # Hide camera frame
        if hasattr(self, 'camera_frame'):
            self.camera_frame.place_forget()
            
        # Close popups
        for popup_attr in ['popup_frame', 'manual_entry_frame', 'timeout_popup', 
                          'payment_popup', 'transaction_id_popup', 'thank_you_popup',
                          'stripe_confirm_popup']:
            if hasattr(self, popup_attr) and getattr(self, popup_attr):
                try:
                    getattr(self, popup_attr).destroy()
                    setattr(self, popup_attr, None)
                except:
                    pass



    def _on_touch(self, event):
        """Handle touch events in Cart mode."""
        x, y = event.x, event.y
        logging.info(f"Touch in Cart mode at ({x}, {y})")
        self._on_activity()

    def _on_activity(self, event=None):
        """Reset inactivity timer on any user activity."""
        # Reset inactivity timer
        self.last_activity_ts = time.time()
        
        # Cancel any existing timeout popup
        if hasattr(self, 'timeout_popup') and self.timeout_popup:
            self._cancel_timeout_popup()

    def _on_key(self, event):
        """Handle keyboard input for barcode scanning."""
        if event.char == '\r' or event.char == '\n':  # Enter key
            barcode = self.barcode_buffer.strip()
            self.barcode_buffer = ""
            
            if barcode:
                logging.info(f"CartMode: Barcode scanned: {barcode}")
                self.scan_item(barcode)
        elif event.char.isprintable():
            self.barcode_buffer += event.char

    def _generate_transaction_id(self):
        """Generate a unique transaction ID in format YYDDD###."""
        try:
            from datetime import datetime
            
            # Get current date components
            now = datetime.now()
            year_last_two = int(now.strftime("%y"))  # Convert to int
            day_of_year = int(now.strftime("%j"))    # Convert to int
            
            # Get the current transaction count for today
            transaction_count_file = Path.home() / "SelfCheck" / "Logs" / f"transaction_count_{year_last_two:02d}{day_of_year:03d}.txt"
            
            # Create directory if it doesn't exist
            transaction_count_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Get current count or start at 0
            current_count = 0
            if transaction_count_file.exists():
                try:
                    with open(transaction_count_file, 'r') as f:
                        current_count = int(f.read().strip())
                except (ValueError, IOError) as e:
                    logging.error(f"Error reading transaction count: {e}")
            
            # Increment count
            new_count = current_count + 1
            
            # Save new count
            try:
                with open(transaction_count_file, 'w') as f:
                    f.write(str(new_count))
            except IOError as e:
                logging.error(f"Error saving transaction count: {e}")
            
            # Format transaction ID: YYDDD### (e.g., 25236001)
            transaction_id = f"{year_last_two:02d}{day_of_year:03d}{new_count:03d}"
            
            logging.info(f"Generated transaction ID: {transaction_id}")
            return transaction_id
            
        except Exception as e:
            logging.error(f"Error generating transaction ID: {e}")
            # Fallback to a simple timestamp-based ID
            fallback_id = f"T{int(time.time())}"
            logging.info(f"Using fallback transaction ID: {fallback_id}")
            return fallback_id

    def _reload_tax_rate(self):
        """Reload the tax rate from Tax.json to ensure it's current."""
        tax_path = CRED_DIR / "Tax.json"
        if tax_path.exists():
            try:
                with open(tax_path, 'r') as f:
                    data = json.load(f)
                    self.tax_rate = float(data.get("rate", 2.9))
                    logging.info(f"Reloaded tax rate from Tax.json: {self.tax_rate}%")
            except (json.JSONDecodeError, ValueError) as e:
                logging.error(f"Error reloading tax rate: {e}")
                self.tax_rate = 2.9  # Default to 2.9% if there's an error

    def _create_ui(self):
        """Create the cart UI elements."""
        # Show main background
        self.label.place(x=0, y=0, width=WINDOW_W, height=WINDOW_H)
        
        try:
            # Load background image
            self.base_bg = self._load_bg()
            self._render_base()
            logging.info("CartMode: Background rendered")
        except Exception as e:
            logging.error(f"CartMode: Error loading background: {e}")
            # Create a simple background
            self.base_bg = Image.new("RGB", (WINDOW_W, WINDOW_H), (255, 255, 255))
            self._render_base()
        
        try:
            # Create receipt area (left side, 2 inches down)
            self._create_receipt_area()
            
            # Create totals area (lower right)
            self._create_totals_area()
            
            # Create buttons (Cancel Order, Manual Entry, Pay Now)
            self._create_cancel_button()
            
            # Update UI with current cart items
            self._update_receipt()
            self._update_totals()
        except Exception as e:
            logging.error(f"CartMode: Error creating UI elements: {e}")
            import traceback
            logging.error(traceback.format_exc())

        # Reset activity timestamp to ensure full 45 seconds
        self.last_activity_ts = time.time()

    def _load_bg(self):
        """Load the cart background image."""
        bg_path = Path.home() / "SelfCheck" / "SysPics" / "Cart.png"
        if bg_path.exists():
            try:
                with Image.open(bg_path) as im:
                    if im.mode in ("RGBA", "P"):
                        im = im.convert("RGB")
                    # Full screen - no letterboxing
                    return im.resize((WINDOW_W, WINDOW_H), Image.LANCZOS)
            except Exception as e:
                logging.error(f"Error loading cart background: {e}")
        
        # Fallback to white background
        return Image.new("RGB", (WINDOW_W, WINDOW_H), (255, 255, 255))

    def _render_base(self):
        """Display the background image."""
        try:
            self.tk_img = ImageTk.PhotoImage(self.base_bg)
            self.label.configure(image=self.tk_img)
            self.label.lift()
        except Exception as e:
            logging.error(f"Error rendering base: {e}")
            # Fallback to plain background
            self.label.configure(bg="white")

    def _create_receipt_area(self):
        """Create the scrollable receipt area."""
        # Add "Tap Item for Edits" label above receipt area
        tap_label = tk.Label(self.root, text="Tap Item for Edits", 
                           font=("Arial", 14, "bold"), bg="#3498db", fg="white")
        tap_label.place(x=50, y=248, width=WINDOW_W//4, height=30)
        
        # Main frame for receipt area (left side, 2 inches down + 1 inch)
        # Original width=WINDOW_W//2, reducing by half makes it width=WINDOW_W//4
        self.receipt_frame = tk.Frame(self.root, bg="white", bd=2, relief=tk.GROOVE)
        self.receipt_frame.place(x=50, y=288, width=WINDOW_W//4, height=WINDOW_H-400)
        
        # Canvas for scrolling
        self.receipt_canvas = tk.Canvas(self.receipt_frame, bg="white", highlightthickness=0)
        self.receipt_scrollbar = tk.Scrollbar(self.receipt_frame, orient=tk.VERTICAL, 
                                            command=self.receipt_canvas.yview)
        self.receipt_canvas.configure(yscrollcommand=self.receipt_scrollbar.set)
        
        # Layout
        self.receipt_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.receipt_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Frame to hold receipt items
        self.receipt_items_frame = tk.Frame(self.receipt_canvas, bg="white")
        self.receipt_canvas.create_window((0, 0), window=self.receipt_items_frame, anchor=tk.NW)
        
        # Configure canvas scrolling
        self.receipt_items_frame.bind("<Configure>", 
                                     lambda e: self.receipt_canvas.configure(
                                         scrollregion=self.receipt_canvas.bbox("all")))

    def _create_totals_area(self):
        """Create the totals display area."""
        # Frame for totals (lower right, raised by 1 inch and moved up more to make room for Pay Now button)
        # Original y=WINDOW_H-496, moving up by another 50 pixels makes it y=WINDOW_H-546
        self.totals_frame = tk.Frame(self.root, bg="white", bd=2, relief=tk.GROOVE)
        self.totals_frame.place(x=WINDOW_W//2 + 100, y=WINDOW_H-546, 
                          width=WINDOW_W//2 - 150, height=396)
        
        # Will be populated in _update_totals()

    def _create_cancel_button(self):
        """Create the cancel order button."""
        # Align with left side of totals frame and move up
        cancel_button = tk.Button(self.root, text="Cancel Order", font=("Arial", 20, "bold"),
                                bg="#e74c3c", fg="white", bd=2, relief=tk.RAISED,
                                command=self._cancel_order)
        cancel_button.place(x=WINDOW_W//2 + 100, y=WINDOW_H-596, width=200, height=50)
    
        # Add Manual Entry button above Cancel Order
        manual_entry_button = tk.Button(self.root, text="Manual Entry", font=("Arial", 20, "bold"),
                                      bg="#3498db", fg="white", bd=2, relief=tk.RAISED,
                                      command=self._show_manual_entry)
        manual_entry_button.place(x=WINDOW_W//2 + 100, y=WINDOW_H-646, width=200, height=50)

        # Add Coupons/Promos button above Manual Entry
        discount_button = tk.Button(self.root, text="Coupons/Promos", font=("Arial", 16, "bold"),
                                  bg="#9b59b6", fg="white", bd=2, relief=tk.RAISED,
                                  command=self._show_discount_entry)
        discount_button.place(x=WINDOW_W//2 + 100, y=WINDOW_H-696, width=200, height=50)
        
    
        # Add Pay Now button at the bottom
        pay_now_button = tk.Button(self.root, text="Pay Now", font=("Arial", 24, "bold"),
                                 bg="#27ae60", fg="white", bd=2, relief=tk.RAISED,
                                 command=self._pay_now)
        pay_now_button.place(x=WINDOW_W//2 + 100, y=WINDOW_H-150, width=WINDOW_W//2 - 150, height=70)

    def _update_receipt(self):
        """Update the receipt display with current cart items."""
        if not hasattr(self, 'receipt_items_frame') or not self.receipt_items_frame:
            return
        
        # Clear existing items
        for widget in self.receipt_items_frame.winfo_children():
            widget.destroy()
        
        if not self.cart_items:
            # Show empty cart message
            empty_label = tk.Label(self.receipt_items_frame, 
                                  text="Cart is empty\nScan items to begin", 
                                  font=("Arial", 14), bg="white", fg="gray")
            empty_label.pack(pady=20)
            return
        
        # Add items to receipt
        for upc, item in self.cart_items.items():
            item_frame = tk.Frame(self.receipt_items_frame, bg="white", bd=1, relief=tk.SOLID)
            item_frame.pack(fill=tk.X, padx=5, pady=2)
            
            # Make item frame clickable for editing
            item_frame.bind("<Button-1>", lambda e, u=upc: self._edit_item(u))
            
            # Item name (truncate if too long)
            name = item["name"]
            if len(name) > 20:
                name = name[:17] + "..."
            
            name_label = tk.Label(item_frame, text=name, font=("Arial", 12, "bold"), 
                                 bg="white", anchor="w")
            name_label.pack(fill=tk.X, padx=5, pady=2)
            name_label.bind("<Button-1>", lambda e, u=upc: self._edit_item(u))
            
            # Price and quantity info
            info_text = f"${item['price']:.2f} x {item['qty']} = ${item['price'] * item['qty']:.2f}"
            info_label = tk.Label(item_frame, text=info_text, font=("Arial", 10), 
                                 bg="white", anchor="w")
            info_label.pack(fill=tk.X, padx=5, pady=(0, 2))
            info_label.bind("<Button-1>", lambda e, u=upc: self._edit_item(u))
        
        # Update scroll region
        self.receipt_items_frame.update_idletasks()
        self.receipt_canvas.configure(scrollregion=self.receipt_canvas.bbox("all"))

    def _show_discount_entry(self):
        """Show discount code entry popup with numeric keypad."""
        # Reset activity timestamp to prevent timeout during entry
        self._on_activity()
        
        # Create popup frame
        self.discount_entry_frame = tk.Frame(self.root, bg="white", bd=3, relief=tk.RAISED)
        self.discount_entry_frame.place(relx=0.5, rely=0.5, width=800, height=700, anchor=tk.CENTER)

        
        # Title
        title_label = tk.Label(self.discount_entry_frame, 
                             text="Enter Coupon or Promo Code", 
                             font=("Arial", 24, "bold"), 
                             bg="white")
        title_label.pack(pady=(20, 10))
        
        # Entry field
        self.discount_code_var = tk.StringVar()
        entry_frame = tk.Frame(self.discount_entry_frame, bg="white")
        entry_frame.pack(pady=20)
        
        entry_field = tk.Entry(entry_frame, 
                             textvariable=self.discount_code_var, 
                             font=("Arial", 24), 
                             width=20, 
                             justify=tk.CENTER)
        entry_field.pack(side=tk.LEFT, padx=10)
        entry_field.focus_set()  # Set focus to the entry field
        
        # Keyboard toggle button
        self.keyboard_mode = "numeric"  # Start with numeric keyboard
        self.keyboard_toggle_btn = tk.Button(entry_frame, 
                                           text="ABC", 
                                           font=("Arial", 18), 
                                           bg="#3498db", fg="white",
                                           command=self._toggle_keyboard_mode)
        self.keyboard_toggle_btn.pack(side=tk.LEFT, padx=10)
        
        # Create container for keyboard
        self.keyboard_container = tk.Frame(self.discount_entry_frame, bg="white")
        self.keyboard_container.pack(pady=20, fill=tk.BOTH, expand=True)
        
        # Show numeric keyboard initially
        self._show_numeric_keyboard()
        
        # Button frame
        button_frame = tk.Frame(self.discount_entry_frame, bg="white")
        button_frame.pack(pady=(20, 20), fill=tk.X, padx=20)
        
        # Cancel button
        cancel_btn = tk.Button(button_frame, 
                             text="Cancel", 
                             font=("Arial", 18), 
                             command=self._close_discount_entry,
                             bg="#e74c3c", fg="white",
                             height=2)
        cancel_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Submit button
        submit_btn = tk.Button(button_frame, 
                             text="Apply Discount", 
                             font=("Arial", 18, "bold"), 
                             command=self._process_discount_code,
                             bg="#27ae60", fg="white",
                             height=2)
        submit_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Bind keyboard events
        self.root.bind("<Key>", self._discount_key_press)

    def _toggle_keyboard_mode(self):
        """Toggle between numeric and QWERTY keyboard."""
        if self.keyboard_mode == "numeric":
            self.keyboard_mode = "qwerty"
            self.keyboard_toggle_btn.config(text="123")
            self._show_qwerty_keyboard()
        else:
            self.keyboard_mode = "numeric"
            self.keyboard_toggle_btn.config(text="ABC")
            self._show_numeric_keyboard()

    def _show_numeric_keyboard(self):
        """Show numeric keyboard in the container."""
        # Clear existing keyboard
        for widget in self.keyboard_container.winfo_children():
            widget.destroy()
        
        # Create number buttons
        buttons = [
            ['1', '2', '3'],
            ['4', '5', '6'],
            ['7', '8', '9'],
            ['0', 'Backspace']
        ]
        
        for row_idx, row in enumerate(buttons):
            row_frame = tk.Frame(self.keyboard_container, bg="white")
            row_frame.pack(fill=tk.X, pady=5)
            
            for col_idx, btn_text in enumerate(row):
                if btn_text == 'Backspace':
                    # Backspace button
                    btn = tk.Button(row_frame, 
                                  text=btn_text, 
                                  font=("Arial", 18), 
                                  bg="#e74c3c", fg="white",
                                  width=10, height=2,
                                  command=self._discount_backspace)
                    btn.pack(side=tk.LEFT, padx=5, pady=5, expand=True)
                else:
                    # Number button
                    btn = tk.Button(row_frame, 
                                  text=btn_text, 
                                  font=("Arial", 24), 
                                  bg="#3498db", fg="white",
                                  width=4, height=2,
                                  command=lambda b=btn_text: self._discount_add_char(b))
                    btn.pack(side=tk.LEFT, padx=5, pady=5, expand=True)

    def _show_qwerty_keyboard(self):
        """Show QWERTY keyboard in the container."""
        # Clear existing keyboard
        for widget in self.keyboard_container.winfo_children():
            widget.destroy()
        
        # Create QWERTY keyboard layout
        rows = [
            ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
            ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
            ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L'],
            ['Z', 'X', 'C', 'V', 'B', 'N', 'M', 'Backspace']
        ]
        
        for row_idx, row in enumerate(rows):
            row_frame = tk.Frame(self.keyboard_container, bg="white")
            row_frame.pack(fill=tk.X, pady=5)
            
            # Add padding for keyboard layout alignment
            if row_idx == 2:  # A-L row
                tk.Label(row_frame, text="", width=1, bg="white").pack(side=tk.LEFT)
            elif row_idx == 3:  # Z-M row
                tk.Label(row_frame, text="", width=2, bg="white").pack(side=tk.LEFT)
            
            for btn_text in row:
                if btn_text == 'Backspace':
                    # Backspace button
                    btn = tk.Button(row_frame, 
                                  text=btn_text, 
                                  font=("Arial", 18), 
                                  bg="#e74c3c", fg="white",
                                  width=10, height=2,
                                  command=self._discount_backspace)
                    btn.pack(side=tk.LEFT, padx=5, pady=5, expand=True)
                else:
                    # Letter/number button
                    btn = tk.Button(row_frame, 
                                  text=btn_text, 
                                  font=("Arial", 20), 
                                  bg="#3498db", fg="white",
                                  width=3, height=2,
                                  command=lambda b=btn_text: self._discount_add_char(b))
                    btn.pack(side=tk.LEFT, padx=5, pady=5)

    def _discount_add_char(self, char):
        """Add a character to the discount code entry."""
        current = self.discount_code_var.get()
        self.discount_code_var.set(current + char)

    def _discount_backspace(self):
        """Remove the last character from the discount code entry."""
        current = self.discount_code_var.get()
        self.discount_code_var.set(current[:-1])

    def _discount_key_press(self, event):
        """Handle keyboard input for discount code entry."""
        if not hasattr(self, 'discount_entry_frame') or not self.discount_entry_frame:
            return
            
        if event.char.isalnum():
            # Add alphanumeric character (convert to uppercase)
            self._discount_add_char(event.char.upper())
        elif event.keysym == 'BackSpace':
            # Backspace
            self._discount_backspace()
        elif event.keysym == 'Return':
            # Enter
            self._process_discount_code()

    def _close_discount_entry(self):
        """Close the discount entry popup."""
        if hasattr(self, 'discount_entry_frame') and self.discount_entry_frame:
            self.discount_entry_frame.destroy()
            self.discount_entry_frame = None
            
        # Unbind keyboard events
        self.root.unbind("<Key>")
        self.root.bind("<Key>", self._on_key)  # Restore original key binding
        
        # Reset activity timestamp
        self._on_activity()

    def _process_discount_code(self):
        """Process the entered discount code."""
        # Get the entered code
        code = self.discount_code_var.get().strip()
        
        if not code:
            self._show_discount_error("Please enter a discount code")
            return
        
        logging.info(f"Processing discount code: {code}")
        
        # Close the entry popup
        self._close_discount_entry()
        
        # Look up the discount in the spreadsheet
        try:
            discount_info = self._get_discount_info(code)
            
            if not discount_info:
                self._show_discount_error("Invalid discount code")
                return
            
            # Check if the discount is expired
            if not self._check_discount_expiration(discount_info):
                self._show_discount_error("This discount has expired")
                return
            
            # Check if one-time use and already used
            if not self._check_discount_usage(discount_info):
                last_used = discount_info.get('last_used', 'Unknown date')
                self._show_discount_error(f"This discount was already used on {last_used}")
                return
            
            # Apply the discount
            self._apply_discount(discount_info)
            
        except Exception as e:
            logging.error(f"Error processing discount: {e}")
            import traceback
            logging.error(traceback.format_exc())
            self._show_discount_error("Error processing discount")

    def _get_discount_info(self, code):
        """Look up discount information from the Discounts tab."""
        try:
            # Connect to Google Sheet
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_file(str(GS_CRED_PATH), scopes=scopes)
            gc = gspread.authorize(creds)
            
            # Open the Discounts tab
            sheet = gc.open(GS_SHEET_NAME).worksheet("Discounts")
            
            # Get all discount data
            all_data = sheet.get_all_values()
            
            # Find the header row to map column indices
            headers = all_data[0] if all_data else []
            
            # Map column indices
            col_indices = {
                'code': headers.index('Code') if 'Code' in headers else 0,
                'type': headers.index('Discount Type') if 'Discount Type' in headers else 1,
                'once': headers.index('Once') if 'Once' in headers else 2,
                'expiration': headers.index('Expiration') if 'Expiration' in headers else 3,
                'dollars': headers.index('Dollars') if 'Dollars' in headers else 4,
                'percent': headers.index('Percent%') if 'Percent%' in headers else 5,
                'total': headers.index('Total') if 'Total' in headers else 6,
                'category': headers.index('Category') if 'Category' in headers else 7,
                'item1': headers.index('Item 1') if 'Item 1' in headers else 8,
                'item2': headers.index('Item 2') if 'Item 2' in headers else 9,
                'item3': headers.index('Item 3') if 'Item 3' in headers else 10,
                'item4': headers.index('Item 4') if 'Item 4' in headers else 11,
                'item5': headers.index('Item 5') if 'Item 5' in headers else 12,
                'last_used': headers.index('Last Used') if 'Last Used' in headers else 13
            }
            
            # Search for the code
            for row in all_data[1:]:  # Skip header row
                if not row:
                    continue
                    
                if row[col_indices['code']].strip().upper() == code.upper():
                    # Found the discount code, create a dictionary with the information
                    discount_info = {
                        'row_index': all_data.index(row) + 1,  # 1-based index for gspread
                        'code': row[col_indices['code']],
                        'type': row[col_indices['type']],
                        'once': row[col_indices['once']].upper() == 'TRUE',
                        'expiration': row[col_indices['expiration']],
                        'dollars': row[col_indices['dollars']],
                        'percent': row[col_indices['percent']],
                        'total': row[col_indices['total']].upper() == 'TRUE',
                        'category': row[col_indices['category']],
                        'items': [
                            row[col_indices['item1']],
                            row[col_indices['item2']],
                            row[col_indices['item3']],
                            row[col_indices['item4']],
                            row[col_indices['item5']]
                        ],
                        'last_used': row[col_indices['last_used']]
                    }
                    
                    # Store the column indices for later updates
                    self.discount_col_indices = col_indices
                    
                    return discount_info
            
            # Code not found
            return None
            
        except Exception as e:
            logging.error(f"Error getting discount info: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return None

    def _check_discount_expiration(self, discount_info):
        """Check if the discount has expired."""
        expiration_str = discount_info.get('expiration', '')
        if not expiration_str:
            return True  # No expiration date, so it's valid
        
        try:
            # Parse the expiration date
            # Try different formats
            for fmt in ['%m/%d/%Y %H:%M:%S', '%m/%d/%Y']:
                try:
                    expiration_date = datetime.strptime(expiration_str, fmt)
                    break
                except ValueError:
                    continue
            else:
                # If no format worked
                logging.warning(f"Could not parse expiration date: {expiration_str}")
                return True  # Allow it if we can't parse the date
            
            # Compare with current date
            current_date = datetime.now()
            return current_date <= expiration_date
            
        except Exception as e:
            logging.error(f"Error checking discount expiration: {e}")
            return True  # Allow it if there's an error

    def _check_discount_usage(self, discount_info):
        """Check if a one-time use discount has already been used."""
        if not discount_info.get('once', False):
            return True  # Not a one-time use discount, so it's valid
        
        last_used = discount_info.get('last_used', '')
        return not bool(last_used.strip())  # Valid if last_used is empty

    def _show_discount_error(self, message):
        """Show an error message for discount processing."""
        messagebox.showerror("Discount Error", message)

    def _apply_discount(self, discount_info):
        """Apply the discount to the cart."""
        # Store the discount info for receipt printing and final processing
        self.current_discount = discount_info
        
        # Check if it's a dollar amount or percentage discount
        dollar_str = discount_info.get('dollars', '').strip()
        percent_str = discount_info.get('percent', '').strip()
        
        if dollar_str and percent_str:
            self._show_discount_error("Invalid discount: both dollar and percentage values are set")
            self.current_discount = None
            return
        
        try:
            # Apply to total or specific items
            if discount_info.get('total', False):
                # Apply to subtotal
                if dollar_str:
                    # Dollar amount discount
                    dollar_amount = float(dollar_str)
                    self._apply_dollar_discount_to_total(dollar_amount)
                elif percent_str:
                    # Percentage discount
                    percent = float(percent_str)
                    self._apply_percent_discount_to_total(percent)
            else:
                # Apply to specific items
                items = [item for item in discount_info.get('items', []) if item.strip()]
                if not items:
                    self._show_discount_error("No items specified for item-specific discount")
                    self.current_discount = None
                    return
                    
                if dollar_str:
                    # Dollar amount discount per item
                    dollar_amount = float(dollar_str)
                    self._apply_dollar_discount_to_items(dollar_amount, items)
                elif percent_str:
                    # Percentage discount per item
                    percent = float(percent_str)
                    self._apply_percent_discount_to_items(percent, items)
            
            # Update the UI
            self._update_totals()
            
            # Show success message
            messagebox.showinfo("Discount Applied", 
                              f"{discount_info.get('type', 'Discount')} has been applied to your order")
            
        except ValueError as e:
            logging.error(f"Error parsing discount values: {e}")
            self._show_discount_error("Invalid discount value")
            self.current_discount = None
        except Exception as e:
            logging.error(f"Error applying discount: {e}")
            self._show_discount_error("Error applying discount")
            self.current_discount = None
    def _apply_dollar_discount_to_total(self, amount):
        """Apply a fixed dollar amount discount to the subtotal."""
        # Calculate current subtotal
        subtotal = sum(item["price"] * item["qty"] for item in self.cart_items.values())
        
        # Limit discount to subtotal amount
        self.discount_amount = min(amount, subtotal)
        self.discount_type = "dollar_total"
        
        logging.info(f"Applied ${self.discount_amount:.2f} discount to subtotal")

    def _apply_percent_discount_to_total(self, percent):
        """Apply a percentage discount to the subtotal."""
        # Calculate current subtotal
        subtotal = sum(item["price"] * item["qty"] for item in self.cart_items.values())
        
        # Calculate discount amount
        self.discount_amount = subtotal * (percent / 100)
        self.discount_type = "percent_total"
        
        logging.info(f"Applied {percent}% discount (${self.discount_amount:.2f}) to subtotal")

    def _apply_dollar_discount_to_items(self, amount, item_upcs):
        """Apply a fixed dollar amount discount to specific items."""
        total_discount = 0
        discount_count = 0
        
        # Convert all UPCs to strings for comparison
        item_upcs = [str(upc).strip() for upc in item_upcs if str(upc).strip()]
        
        for upc, item in self.cart_items.items():
            # Check if this item's UPC matches any in the discount list
            if any(self._match_upc(upc, discount_upc) for discount_upc in item_upcs):
                # Apply discount for each quantity of this item
                item_discount = min(amount, item["price"]) * item["qty"]
                total_discount += item_discount
                discount_count += item["qty"]
        
        self.discount_amount = total_discount
        self.discount_type = "dollar_items"
        self.discount_items = item_upcs
        self.discount_item_count = discount_count
        
        logging.info(f"Applied ${amount:.2f} discount to {discount_count} items, total discount: ${total_discount:.2f}")

    def _apply_percent_discount_to_items(self, percent, item_upcs):
        """Apply a percentage discount to specific items."""
        total_discount = 0
        discount_count = 0
        
        # Convert all UPCs to strings for comparison
        item_upcs = [str(upc).strip() for upc in item_upcs if str(upc).strip()]
        
        for upc, item in self.cart_items.items():
            # Check if this item's UPC matches any in the discount list
            if any(self._match_upc(upc, discount_upc) for discount_upc in item_upcs):
                # Apply discount for each quantity of this item
                item_discount = item["price"] * (percent / 100) * item["qty"]
                total_discount += item_discount
                discount_count += item["qty"]
        
        self.discount_amount = total_discount
        self.discount_type = "percent_items"
        self.discount_items = item_upcs
        self.discount_item_count = discount_count
        
        logging.info(f"Applied {percent}% discount to {discount_count} items, total discount: ${total_discount:.2f}")

    def _match_upc(self, cart_upc, discount_upc):
        """Check if cart UPC matches discount UPC, handling variants."""
        if not cart_upc or not discount_upc:
            return False
            
        # Direct match
        if str(cart_upc).strip() == str(discount_upc).strip():
            return True
            
        # Try variants
        cart_variants = upc_variants_from_scan(cart_upc)
        discount_variants = upc_variants_from_sheet(discount_upc)
        
        # Check for any overlap
        return any(cv == dv for cv in cart_variants for dv in discount_variants)

    def _update_discount_usage(self):
        """Update the spreadsheet with discount usage timestamp."""
        if not hasattr(self, 'current_discount') or not self.current_discount:
            logging.info("No discount to update usage for")
            return
            
        # Only update if it's a one-time use discount
        if not self.current_discount.get('once', False):
            logging.info("Not a one-time use discount, skipping usage update")
            return
            
        try:
            # Connect to Google Sheet
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_file(str(GS_CRED_PATH), scopes=scopes)
            gc = gspread.authorize(creds)
            
            # Open the Discounts tab
            sheet = gc.open(GS_SHEET_NAME).worksheet("Discounts")
            
            # Get row index and last_used column index
            row_index = self.current_discount.get('row_index')
            
            if not hasattr(self, 'discount_col_indices') or not self.discount_col_indices:
                logging.error("Missing column indices for discount update")
                # Try to get column indices directly
                all_data = sheet.get_all_values()
                headers = all_data[0] if all_data else []
                last_used_col = headers.index('Last Used') + 1 if 'Last Used' in headers else 14  # Default to column N
            else:
                last_used_col = self.discount_col_indices.get('last_used') + 1  # Convert to 1-based index
            
            if not row_index:
                logging.error(f"Missing row index ({row_index}) for discount update")
                return
                
            # Current timestamp
            timestamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
            
            # Log what we're about to do
            logging.info(f"Updating discount usage: Sheet={GS_SHEET_NAME}, Tab=Discounts, Row={row_index}, Col={last_used_col}, Value={timestamp}")
            
            # Update the cell
            sheet.update_cell(row_index, last_used_col, timestamp)
            logging.info(f"Updated discount usage timestamp for code {self.current_discount.get('code')} to {timestamp}")
            
        except Exception as e:
            logging.error(f"Error updating discount usage: {e}")
            import traceback
            logging.error(traceback.format_exc())


    def _clear_discount_info(self):
        """Clear all discount-related information."""
        if hasattr(self, 'discount_amount'):
            delattr(self, 'discount_amount')
        if hasattr(self, 'discount_type'):
            delattr(self, 'discount_type')
        if hasattr(self, 'current_discount'):
            delattr(self, 'current_discount')
        if hasattr(self, 'discount_items'):
            delattr(self, 'discount_items')
        if hasattr(self, 'discount_item_count'):
            delattr(self, 'discount_item_count')
        logging.info("Cleared all discount information")



#     *******************************End of Dicount Logic ***********************************************


    def _update_totals(self):
        """Update the totals display."""
        if not hasattr(self, 'totals_frame'):
            return
            
        # Calculate subtotal
        subtotal = sum(item["price"] * item["qty"] for item in self.cart_items.values())
        
        # Apply discount if any
        discount_amount = getattr(self, 'discount_amount', 0)
        
        # Adjust subtotal after discount
        adjusted_subtotal = subtotal - discount_amount
        
        # Ensure adjusted subtotal is not negative
        adjusted_subtotal = max(0, adjusted_subtotal)
        
        # Calculate tax
        taxable_subtotal = sum(
            item["price"] * item["qty"] 
            for item in self.cart_items.values() if item["taxable"]
        )
        
        # If we have a discount, adjust taxable subtotal proportionally
        if discount_amount > 0 and subtotal > 0:
            # For total discounts, reduce taxable amount proportionally
            if hasattr(self, 'discount_type') and self.discount_type in ['dollar_total', 'percent_total']:
                taxable_subtotal = max(0, taxable_subtotal * (adjusted_subtotal / subtotal))
            # For item-specific discounts, we need to check which items were discounted
            elif hasattr(self, 'discount_type') and self.discount_type in ['dollar_items', 'percent_items'] and hasattr(self, 'discount_items'):
                # Calculate tax reduction for discounted taxable items
                tax_reduction = 0
                for upc, item in self.cart_items.items():
                    if item["taxable"] and any(self._match_upc(upc, discount_upc) for discount_upc in self.discount_items):
                        if self.discount_type == 'dollar_items':
                            # Reduce by dollar amount per item, limited by item price
                            item_discount = min(float(getattr(self, 'current_discount', {}).get('dollars', 0)), item["price"]) * item["qty"]
                            tax_reduction += item_discount
                        else:  # percent_items
                            # Reduce by percentage of item price
                            percent = float(getattr(self, 'current_discount', {}).get('percent', 0))
                            item_discount = item["price"] * (percent / 100) * item["qty"]
                            tax_reduction += item_discount
                
                # Adjust taxable subtotal
                taxable_subtotal = max(0, taxable_subtotal - tax_reduction)
        
        tax_amount = taxable_subtotal * (self.tax_rate / 100)
        total = adjusted_subtotal + tax_amount
        
        # Store the calculated total as an instance variable
        self.final_total = total
        
        # Update the display
        total_items = sum(item["qty"] for item in self.cart_items.values())
        
        # Clear existing widgets
        for widget in self.totals_frame.winfo_children():
            widget.destroy()
        
        # Business name
        business_label = tk.Label(self.totals_frame, text=self.business_name, 
                                font=("Arial", 16, "bold"), bg="white")
        business_label.pack(anchor=tk.W, pady=(0, 5))
        
        # Machine ID
        machine_label = tk.Label(self.totals_frame, text=f"Machine: {self.machine_id}", 
                               font=("Arial", 12), bg="white")
        machine_label.pack(anchor=tk.W)
        
        # Transaction ID
        txn_label = tk.Label(self.totals_frame, text=f"Transaction #: {self.transaction_id}", 
                           font=("Arial", 12), bg="white")
        txn_label.pack(anchor=tk.W)
        
        # Date and time
        now = datetime.now()
        date_label = tk.Label(self.totals_frame, text=now.strftime("%m/%d/%Y %H:%M:%S"), 
                            font=("Arial", 12), bg="white")
        date_label.pack(anchor=tk.W, pady=(0, 10))
        
        # Horizontal line
        separator = ttk.Separator(self.totals_frame, orient='horizontal')
        separator.pack(fill=tk.X, pady=5)
        
        # Items count
        items_label = tk.Label(self.totals_frame, text=f"Items: {total_items}", 
                             font=("Arial", 14), bg="white")
        items_label.pack(anchor=tk.W, pady=(5, 0))
        
        # Subtotal
        subtotal_label = tk.Label(self.totals_frame, text=f"Subtotal: ${subtotal:.2f}", 
                                font=("Arial", 14), bg="white")
        subtotal_label.pack(anchor=tk.W)
        
        # Discount if applicable
        if discount_amount > 0:
            discount_type_name = "Coupon"
            if hasattr(self, 'current_discount') and self.current_discount:
                discount_type_name = self.current_discount.get('type', 'Coupon')
                
            discount_label = tk.Label(self.totals_frame, text=f"Discount ({discount_type_name}): -${discount_amount:.2f}", 
                                    font=("Arial", 14), bg="white", fg="red")
            discount_label.pack(anchor=tk.W)
        
        # Tax
        tax_label = tk.Label(self.totals_frame, text=f"Tax ({self.tax_rate}%): ${tax_amount:.2f}", 
                           font=("Arial", 14), bg="white")
        tax_label.pack(anchor=tk.W)
        
        # Total
        total_label = tk.Label(self.totals_frame, text=f"Total: ${total:.2f}", 
                             font=("Arial", 16, "bold"), bg="white")
        total_label.pack(anchor=tk.W, pady=(0, 10))


    def scan_item(self, upc):
        """Process a scanned item and add to cart."""
        logging.info(f"Cart: Scanning item {upc}")
        self._on_activity()
        
        # Check if we've reached the maximum number of different items
        if len(self.cart_items) >= 15 and upc not in self.cart_items:
            self._show_error("Maximum number of different items reached (15)")
            return False
            
        # Look up UPC in catalog
        row = self.upc_catalog.get(upc)
        if not row:
            # Try variants
            for variant in upc_variants_from_scan(upc):
                row = self.upc_catalog.get(variant)
                if row:
                    break
                    
        if not row:
            self._show_error(f"Item not found: {upc}")
            return False
            
        # Check if item is already in cart
        if upc in self.cart_items:
            # Check if we've reached the maximum quantity for this item
            if self.cart_items[upc]["qty"] >= 10:
                self._show_error(f"Maximum quantity reached for this item (10)")
                return False
                
            # Increment quantity
            self.cart_items[upc]["qty"] += 1
        else:
            # Add new item to cart
            try:
                # Extract relevant data from row
                name = f"{row[1]} {row[2]} {row[4]}"  # Brand (B=1), Name (C=2), Size (E=4)
                price = float(row[8].replace('$', '').strip())  # Price (I=8)
                taxable = row[9].strip().lower() == 'yes'  # Taxable (J=9)
                image = row[11] if len(row) > 11 else ""  # Image (L=11)
                
                self.cart_items[upc] = {
                    "name": name,
                    "price": price,
                    "taxable": taxable,
                    "image": image,
                    "qty": 1,
                    "row": row
                }
            except (IndexError, ValueError) as e:
                logging.error(f"Error processing item data: {e}")
                self._show_error(f"Error processing item data")
                return False
                
        # Update UI
        self._update_receipt()
        self._update_totals()
        return True


    def _edit_item(self, upc):
        """Show edit options for an item."""
        if upc not in self.cart_items:
            return
        
        item = self.cart_items[upc]
        
        # Create a frame-based popup that stays within our application
        # First, store any existing popup to avoid multiple popups
        if hasattr(self, 'edit_popup_frame') and self.edit_popup_frame:
            self.edit_popup_frame.destroy()
        
        # Create a dark overlay to dim the background
        overlay = tk.Frame(self.root, bg='#000000')
        overlay.place(x=0, y=0, width=WINDOW_W, height=WINDOW_H)
        
        # Create the popup frame
        self.edit_popup_frame = tk.Frame(self.root, bg="white", bd=2, relief=tk.RAISED)
        popup_width = 400
        popup_height = 400
        x_position = (WINDOW_W - popup_width) // 2
        y_position = (WINDOW_H - popup_height) // 2
        self.edit_popup_frame.place(x=x_position, y=y_position, width=popup_width, height=popup_height)
        
        # Title bar
        title_bar = tk.Frame(self.edit_popup_frame, bg="#3498db", height=40)
        title_bar.pack(fill=tk.X)
        
        title_label = tk.Label(title_bar, text="Edit Item", font=("Arial", 16, "bold"), 
                              bg="#3498db", fg="white")
        title_label.pack(side=tk.LEFT, padx=15, pady=5)
        
        # Main container frame
        main_frame = tk.Frame(self.edit_popup_frame, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Item name with wrapping
        name_label = tk.Label(main_frame, text=item["name"], 
                             font=("Arial", 16, "bold"), bg="white",
                             wraplength=360, justify=tk.LEFT)
        name_label.pack(pady=(0, 15), anchor=tk.W)
        
        # Price info
        price_label = tk.Label(main_frame, text=f"Price: ${item['price']:.2f}", 
                              font=("Arial", 14), bg="white")
        price_label.pack(pady=(0, 5), anchor=tk.W)
        
        # Quantity controls with clear visual feedback
        qty_frame = tk.Frame(main_frame, bg="white")
        qty_frame.pack(pady=20)
        
        qty_label = tk.Label(qty_frame, text="Quantity:", font=("Arial", 14, "bold"), bg="white")
        qty_label.pack(side=tk.LEFT, padx=(0, 10))
        
        # Create a StringVar to track changes
        qty_var = tk.StringVar(value=str(item["qty"]))
        
        def update_qty_display():
            qty_label_display.config(text=qty_var.get())
        
        def change_qty(change):
            new_qty = max(1, min(10, int(qty_var.get()) + change))
            qty_var.set(str(new_qty))
            update_qty_display()
        
        # Minus button with better styling
        minus_btn = tk.Button(qty_frame, text="-", font=("Arial", 16, "bold"), 
                             bg="#e74c3c", fg="white", width=2,
                             command=lambda: change_qty(-1))
        minus_btn.pack(side=tk.LEFT, padx=5)
        
        # Quantity display
        qty_label_display = tk.Label(qty_frame, text=str(item["qty"]), 
                                   font=("Arial", 16, "bold"), bg="white", width=2)
        qty_label_display.pack(side=tk.LEFT, padx=10)
        
        # Plus button with better styling
        plus_btn = tk.Button(qty_frame, text="+", font=("Arial", 16, "bold"), 
                            bg="#2ecc71", fg="white", width=2,
                            command=lambda: change_qty(1))
        plus_btn.pack(side=tk.LEFT, padx=5)
        
        # Current total
        total_frame = tk.Frame(main_frame, bg="white")
        total_frame.pack(pady=10, fill=tk.X)
        
        total_label = tk.Label(total_frame, 
                              text=f"Item Total: ${item['price'] * item['qty']:.2f}", 
                              font=("Arial", 14), bg="white")
        total_label.pack(side=tk.LEFT)
        
        # Update total when quantity changes
        def update_total(*args):
            try:
                qty = int(qty_var.get())
                total_label.config(text=f"Item Total: ${item['price'] * qty:.2f}")
            except ValueError:
                pass
        
        qty_var.trace_add("write", update_total)
        
        # Buttons frame
        btn_frame = tk.Frame(main_frame, bg="white")
        btn_frame.pack(pady=20, side=tk.BOTTOM, fill=tk.X)
        
        # Helper function to close popup
        def close_popup():
            if hasattr(self, 'edit_popup_frame') and self.edit_popup_frame:
                self.edit_popup_frame.destroy()
                self.edit_popup_frame = None
            overlay.destroy()
        
        # Remove button
        remove_btn = tk.Button(btn_frame, text="Remove Item", font=("Arial", 14), 
                              bg="#e74c3c", fg="white", padx=10,
                              command=lambda: self._remove_item(upc, close_popup))
        remove_btn.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # Update & Exit button
        update_btn = tk.Button(btn_frame, text="Update & Exit", font=("Arial", 14), 
                              bg="#3498db", fg="white", padx=10,
                              command=lambda: self._update_item_qty(upc, int(qty_var.get()), close_popup))
        update_btn.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # Store reference to overlay for cleanup
        self.edit_overlay = overlay
        
        # Reset activity timestamp
        self._on_activity()
    
    def _remove_item(self, upc, close_callback):
        """Remove an item from the cart."""
        if upc in self.cart_items:
            del self.cart_items[upc]
            close_callback()
            self._update_receipt()
            self._update_totals()
    
    def _update_item_qty(self, upc, new_qty, close_callback):
        """Update the quantity of an item."""
        if upc in self.cart_items:
            # Ensure quantity is within limits
            new_qty = max(1, min(10, new_qty))
            self.cart_items[upc]["qty"] = new_qty
            close_callback()
            self._update_receipt()
            self._update_totals()



    def _show_manual_entry(self):
        """Show manual entry popup with numeric keypad."""
        # Reset activity timestamp to prevent timeout during manual entry
        self._on_activity()
        
        # Create popup frame - now using full screen height but reduced width
        popup_width = int(WINDOW_W * 0.6)  # 60% of screen width
        self.manual_entry_frame = tk.Frame(self.root, bg="white", bd=3, relief=tk.RAISED)
        self.manual_entry_frame.place(relx=0.5, rely=0.5, width=popup_width, height=WINDOW_H-50, anchor=tk.CENTER)
        
        # Use a main container with grid layout for better control
        main_container = tk.Frame(self.manual_entry_frame, bg="white")
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        main_container.grid_columnconfigure(0, weight=1)
        
        # Define row weights - this is crucial for proper layout
        main_container.grid_rowconfigure(0, weight=0)  # Title - fixed size
        main_container.grid_rowconfigure(1, weight=0)  # Entry field - fixed size
        main_container.grid_rowconfigure(2, weight=1)  # Item display - expandable
        main_container.grid_rowconfigure(3, weight=2)  # Keypad - expandable, more space
        main_container.grid_rowconfigure(4, weight=0)  # Enter/Cancel buttons - fixed size
        main_container.grid_rowconfigure(5, weight=0)  # Action buttons - fixed size
        
        # Title
        title_label = tk.Label(main_container, text="Manual Entry", 
                             font=("Arial", 24, "bold"), bg="white")
        title_label.grid(row=0, column=0, pady=(10, 10), sticky="ew")
        
        # Entry field for UPC/PLU
        entry_frame = tk.Frame(main_container, bg="white")
        entry_frame.grid(row=1, column=0, pady=(5, 10), sticky="ew")
        entry_frame.columnconfigure(1, weight=1)
        
        entry_label = tk.Label(entry_frame, text="Enter UPC/PLU:", font=("Arial", 18), bg="white")
        entry_label.grid(row=0, column=0, padx=10)
        
        self.manual_entry_var = tk.StringVar()
        entry_field = tk.Entry(entry_frame, textvariable=self.manual_entry_var, 
                             font=("Arial", 24), width=20, justify=tk.RIGHT)
        entry_field.grid(row=0, column=1, padx=10, sticky="ew")
        
        # Item display area - will be populated when an item is found
        self.item_display_frame = tk.Frame(main_container, bg="white", bd=1, relief=tk.GROOVE)
        self.item_display_frame.grid(row=2, column=0, pady=10, sticky="nsew")
        
        # Initially show a placeholder
        placeholder_label = tk.Label(self.item_display_frame, text="Enter a UPC and press Enter to search", 
                                   font=("Arial", 14), bg="white", fg="#888888")
        placeholder_label.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # These will be created when an item is found
        self.item_name_label = None
        self.item_details_label = None
        self.item_image_label = None
        self.manual_qty_var = tk.IntVar(value=1)
        
        # Numeric keypad - smaller buttons
        keypad_frame = tk.Frame(main_container, bg="#f0f0f0")
        keypad_frame.grid(row=3, column=0, pady=10, sticky="nsew")
        
        # Configure keypad grid
        for i in range(4):  # 4 rows
            keypad_frame.grid_rowconfigure(i, weight=1)
        for i in range(3):  # 3 columns
            keypad_frame.grid_columnconfigure(i, weight=1)
        
        # Create keypad buttons with backspace
        keys = [
            ['7', '8', '9'],
            ['4', '5', '6'],
            ['1', '2', '3'],
            ['0', 'Clear', 'Backspace']
        ]
        
        # Function to handle backspace
        def backspace():
            current = self.manual_entry_var.get()
            self.manual_entry_var.set(current[:-1])
        
        for row_idx, row in enumerate(keys):
            for col_idx, key in enumerate(row):
                # Determine button color and command
                if key == 'Clear':
                    bg_color = "#e74c3c"  # Red
                    command = lambda: self.manual_entry_var.set("")
                elif key == 'Backspace':
                    bg_color = "#f39c12"  # Orange
                    command = backspace
                else:
                    bg_color = "#3498db"  # Blue
                    command = lambda k=key: self.manual_entry_var.set(self.manual_entry_var.get() + k)
                
                # Create button with smaller size
                btn = tk.Button(keypad_frame, text=key, font=("Arial", 14, "bold"),
                              bg=bg_color, fg="white", command=command,
                              width=5, height=1)  # Fixed size for smaller buttons
                btn.grid(row=row_idx, column=col_idx, sticky="nsew", padx=10, pady=10)
        
        # Enter and Cancel buttons
        button_frame = tk.Frame(main_container, bg="#f0f0f0", height=60)
        button_frame.grid(row=4, column=0, pady=5, sticky="ew")
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)
        
        # Cancel button
        cancel_btn = tk.Button(button_frame, text="Cancel", font=("Arial", 16, "bold"),
                             bg="#e74c3c", fg="white", command=self._close_manual_entry)
        cancel_btn.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        
        # Enter button
        enter_btn = tk.Button(button_frame, text="Enter", font=("Arial", 16, "bold"),
                            bg="#27ae60", fg="white", command=self._manual_entry_lookup)
        enter_btn.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
        
        # Action buttons frame (initially empty, will be populated when item is found)
        self.action_buttons_frame = tk.Frame(main_container, bg="#f0f0f0", height=60)
        self.action_buttons_frame.grid(row=5, column=0, pady=5, sticky="ew")
        self.action_buttons_frame.grid_columnconfigure(0, weight=1)
        self.action_buttons_frame.grid_columnconfigure(1, weight=1)
        
        # Hide action buttons initially
        self.action_buttons_frame.grid_remove()
        
        # Set focus to entry field
        entry_field.focus_set()
        
        # Bind Enter key to lookup
        entry_field.bind("<Return>", lambda e: self._manual_entry_lookup())
        
        # Store reference to main container for later use
        self.manual_entry_container = main_container

    def _manual_entry_lookup(self):
        """Look up the entered UPC/PLU."""
        upc = self.manual_entry_var.get().strip()
        logging.info(f"Manual entry lookup for UPC: {upc}")
        
        if not upc:
            logging.warning("Empty UPC entered")
            return
            
        # Look up UPC in catalog
        row = self.upc_catalog.get(upc)
        if not row:
            logging.info(f"UPC {upc} not found directly, trying variants")
            # Try variants
            for variant in upc_variants_from_scan(upc):
                row = self.upc_catalog.get(variant)
                if row:
                    upc = variant  # Use the matched variant
                    logging.info(f"Found variant: {variant}")
                    break
                    
        if not row:
            logging.warning(f"Item not found: {upc}")
            messagebox.showerror("Error", f"Item not found: {upc}")
            return
            
        # Extract item data
        try:
            name = f"{row[1]} {row[2]} {row[4]}"  # Brand (B=1), Name (C=2), Size (E=4)
            price = float(row[8].replace('$', '').strip())  # Price (I=8)
            taxable = row[9].strip().lower() == 'yes'  # Taxable (J=9)
            image_name = row[11] if len(row) > 11 else ""  # Image (L=11)
            
            # Display the item
            self._display_manual_item(name, price, taxable, image_name, upc)
            
        except Exception as e:
            logging.error(f"Error processing item data: {e}")
            import traceback
            logging.error(traceback.format_exc())
            messagebox.showerror("Error", f"Error processing item data: {str(e)}")

    def _display_manual_item(self, name, price, taxable, image_name, upc):
        """Display item details in the manual entry popup."""
        # Clear the item display frame
        for widget in self.item_display_frame.winfo_children():
            widget.destroy()
        
        # Create scrollable frame for item details
        canvas = tk.Canvas(self.item_display_frame, bg="white", highlightthickness=0)
        scrollbar = tk.Scrollbar(self.item_display_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="white")
        
        # Configure canvas
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Create window in canvas for scrollable frame
        canvas.create_window((0, 0), window=scrollable_frame, anchor=tk.NW)
        
        # Configure scrollable frame to update canvas scroll region
        def configure_scroll_region(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # Also set the width of the window to match the canvas width
            canvas.itemconfig(canvas_window, width=canvas.winfo_width())
            
        scrollable_frame.bind("<Configure>", configure_scroll_region)
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor=tk.NW)
        
        # Item name
        self.item_name_label = tk.Label(scrollable_frame, text=name, 
                                      font=("Arial", 16, "bold"), bg="white", 
                                      wraplength=400, justify=tk.LEFT)
        self.item_name_label.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        # Item details
        self.item_details_label = tk.Label(scrollable_frame, 
                                         text=f"Price: ${price:.2f}  Taxable: {'Yes' if taxable else 'No'}", 
                                         font=("Arial", 14), bg="white")
        self.item_details_label.pack(fill=tk.X, padx=10, pady=5)
        
        # Quantity control
        qty_frame = tk.Frame(scrollable_frame, bg="white")
        qty_frame.pack(pady=10)
        
        qty_label = tk.Label(qty_frame, text="QTY:", font=("Arial", 16), bg="white")
        qty_label.pack(side=tk.LEFT, padx=5)
        
        self.manual_qty_var.set(1)  # Reset to 1
        qty_display = tk.Label(qty_frame, textvariable=self.manual_qty_var, 
                             font=("Arial", 16, "bold"), bg="white", width=2)
        qty_display.pack(side=tk.LEFT, padx=5)
        
        def decrease_qty():
            if self.manual_qty_var.get() > 1:
                self.manual_qty_var.set(self.manual_qty_var.get() - 1)
                
        def increase_qty():
            if self.manual_qty_var.get() < 10:
                self.manual_qty_var.set(self.manual_qty_var.get() + 1)
                
        # Changed to simple + and - symbols
        down_btn = tk.Button(qty_frame, text="-", font=("Arial", 16, "bold"), command=decrease_qty)
        down_btn.pack(side=tk.LEFT, padx=5)
        
        up_btn = tk.Button(qty_frame, text="+", font=("Arial", 16, "bold"), command=increase_qty)
        up_btn.pack(side=tk.LEFT, padx=5)
        
        # Image display
        self.item_image_label = tk.Label(scrollable_frame, bg="white")
        self.item_image_label.pack(pady=10)
        
        # Load image
        if image_name:
            self.item_image_label.config(text="Loading image...")
            self._load_product_image(image_name, self.item_image_label, size=(225, 225))
        else:
            self.item_image_label.config(text="No image available")
        
        # Clear action buttons frame
        for widget in self.action_buttons_frame.winfo_children():
            widget.destroy()
        
        # Create action buttons
        add_btn = tk.Button(self.action_buttons_frame, text="Add to Order", 
                          font=("Arial", 16, "bold"), bg="#27ae60", fg="white", 
                          command=self._manual_entry_add)
        add_btn.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        
        cancel_btn = tk.Button(self.action_buttons_frame, text="Cancel", 
                             font=("Arial", 16, "bold"), bg="#e74c3c", fg="white", 
                             command=self._close_manual_entry)
        cancel_btn.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
        
        # Make action buttons visible
        self.action_buttons_frame.grid()
        
        # Store the current UPC for later use
        self.current_manual_upc = upc


    def _manual_entry_add(self):
        """Add manually entered item to cart."""
        if not hasattr(self, 'current_manual_upc'):
            logging.warning("No current UPC to add to cart")
            return
            
        upc = self.current_manual_upc
        qty = self.manual_qty_var.get()
        
        logging.info(f"Adding item to cart: UPC={upc}, QTY={qty}")
        
        # Add to cart
        row = self.upc_catalog.get(upc)
        if not row:
            logging.warning(f"UPC {upc} not found in catalog")
            return
            
        # Check if we've reached the maximum number of different items
        if len(self.cart_items) >= 15 and upc not in self.cart_items:
            messagebox.showerror("Error", "Maximum number of different items reached (15)")
            return
            
        # Check if item is already in cart
        if upc in self.cart_items:
            # Check if adding would exceed the maximum quantity
            current_qty = self.cart_items[upc]["qty"]
            if current_qty + qty > 10:
                messagebox.showerror("Error", f"Maximum quantity reached for this item (10)")
                return
                
            # Update quantity
            self.cart_items[upc]["qty"] = current_qty + qty
            logging.info(f"Updated quantity for {upc} to {current_qty + qty}")
        else:
            # Add new item to cart
            try:
                # Extract relevant data from row
                name = f"{row[1]} {row[2]} {row[4]}"  # Brand (B=1), Name (C=2), Size (E=4)
                price = float(row[8].replace('$', '').strip())  # Price (I=8)
                taxable = row[9].strip().lower() == 'yes'  # Taxable (J=9)
                image = row[11] if len(row) > 11 else ""  # Image (L=11)
                
                self.cart_items[upc] = {
                    "name": name,
                    "price": price,
                    "taxable": taxable,
                    "image": image,
                    "qty": qty,
                    "row": row
                }
                logging.info(f"Added new item to cart: {name}")
            except (IndexError, ValueError) as e:
                logging.error(f"Error processing item data: {e}")
                messagebox.showerror("Error", f"Error processing item data")
                return
                
        # Update UI
        self._update_receipt()
        self._update_totals()
        
        # Close manual entry popup
        self._close_manual_entry()
        
        # Show confirmation
        messagebox.showinfo("Success", "Item added to cart")

    def _close_manual_entry(self):
        """Close the manual entry popup."""
        if hasattr(self, 'manual_entry_frame') and self.manual_entry_frame:
            self.manual_entry_frame.destroy()
            self.manual_entry_frame = None
        
        # Reset activity timestamp
        self._on_activity()

    def _pay_now(self):
        """Handle Pay Now button click."""
        # First, ensure any existing payment popups are destroyed
        self._close_all_payment_popups()
        
        # Calculate the total for display
        subtotal = sum(item["price"] * item["qty"] for item in self.cart_items.values())
        
        # Apply discount if any
        discount_amount = getattr(self, 'discount_amount', 0)
        
        # Adjust subtotal after discount
        adjusted_subtotal = max(0, subtotal - discount_amount)
        
        # Calculate tax on adjusted subtotal
        taxable_subtotal = sum(
            item["price"] * item["qty"] 
            for item in self.cart_items.values() if item["taxable"]
        )
        
        # If we have a discount, adjust taxable subtotal proportionally
        if discount_amount > 0 and subtotal > 0:
            # For total discounts, reduce taxable amount proportionally
            if hasattr(self, 'discount_type') and self.discount_type in ['dollar_total', 'percent_total']:
                taxable_subtotal = max(0, taxable_subtotal * (adjusted_subtotal / subtotal))
            # For item-specific discounts, we need to check which items were discounted
            elif hasattr(self, 'discount_type') and self.discount_type in ['dollar_items', 'percent_items'] and hasattr(self, 'discount_items'):
                # Calculate tax reduction for discounted taxable items
                tax_reduction = 0
                for upc, item in self.cart_items.items():
                    if item["taxable"] and any(self._match_upc(upc, discount_upc) for discount_upc in self.discount_items):
                        if self.discount_type == 'dollar_items':
                            # Reduce by dollar amount per item, limited by item price
                            item_discount = min(float(getattr(self, 'current_discount', {}).get('dollars', 0)), item["price"]) * item["qty"]
                            tax_reduction += item_discount
                        else:  # percent_items
                            # Reduce by percentage of item price
                            percent = float(getattr(self, 'current_discount', {}).get('percent', 0))
                            item_discount = item["price"] * (percent / 100) * item["qty"]
                            tax_reduction += item_discount
                
                # Adjust taxable subtotal
                taxable_subtotal = max(0, taxable_subtotal - tax_reduction)
        
        tax_amount = taxable_subtotal * (self.tax_rate / 100)
        total = adjusted_subtotal + tax_amount
        
        # Store the calculated total as an instance variable
        self.final_total = total
        
        # Log the calculated total
        logging.info(f"Calculated final total: ${self.final_total:.2f}")
        
        # Create payment popup with the correct total
        self._show_payment_popup(self.final_total)



    def _close_all_payment_popups(self):
        """Close all payment-related popups."""
        # Log what we're doing
        logging.info("Closing all payment popups")
        
        # Cancel all payment-related timers
        for timer_attr in ['payment_timeout', 'payment_countdown_after', 
                          'transaction_id_timeout', 'thank_you_timeout',
                          'payment_check_timer', 'stripe_countdown_after']:
            if hasattr(self, timer_attr) and getattr(self, timer_attr):
                try:
                    self.root.after_cancel(getattr(self, timer_attr))
                    setattr(self, timer_attr, None)
                    logging.info(f"Cancelled timer: {timer_attr}")
                except Exception as e:
                    logging.error(f"Error cancelling timer {timer_attr}: {e}")
        
        # Destroy all payment-related popups
        for popup_attr in ['payment_popup', 'payment_timeout_popup', 
                          'transaction_id_popup', 'thank_you_popup',
                          'stripe_confirm_popup']:
            if hasattr(self, popup_attr) and getattr(self, popup_attr):
                try:
                    getattr(self, popup_attr).destroy()
                    setattr(self, popup_attr, None)
                    logging.info(f"Destroyed popup: {popup_attr}")
                except Exception as e:
                    logging.error(f"Error destroying popup {popup_attr}: {e}")
        
        # Reset activity timestamp
        self._on_activity()
        
        # Restore original key binding
        self.root.unbind("<Key>")
        self.root.bind("<Key>", self._on_key)





    def _show_payment_popup(self, total):
        """Show payment options popup."""
        # Cancel any existing timeout
        self._on_activity()
    
        # Create popup frame - ensure we're starting fresh
        self.payment_popup = tk.Frame(self.root, bg="white", bd=3, relief=tk.RAISED)
        self.payment_popup.place(relx=0.5, rely=0.5, width=600, height=500, anchor=tk.CENTER)
    
        # Display total at the top
        total_label = tk.Label(self.payment_popup, 
                             text=f"Total: ${total:.2f}", 
                             font=("Arial", 24, "bold"), 
                             bg="white")
        total_label.pack(pady=(30, 20))
    
        # Load payment method images
        payment_images_dir = Path.home() / "SelfCheck" / "SysPics"
    
        # Load settings
        settings_path = Path.home() / "SelfCheck" / "Cred" / "Settings.json"
        try:
            with open(settings_path, 'r') as f:
                settings = json.load(f)
        except Exception as e:
            logging.error(f"Error loading settings: {e}")
            settings = {
                "payment_options": {
                    "venmo_enabled": True,
                    "cashapp_enabled": True
                },
                "receipt_options": {
                    "print_receipt_enabled": True
                }
            }
    
        # Stripe button (always shown)
        stripe_path = payment_images_dir / "stripe.png"
        if stripe_path.exists():
            try:
                with Image.open(stripe_path) as img:
                    # Resize to appropriate size
                    img = img.resize((400, 100), Image.LANCZOS)
                    stripe_img = ImageTk.PhotoImage(img)
                
                    # Create button with image
                    stripe_btn = tk.Button(self.payment_popup, 
                                         image=stripe_img, 
                                         command=lambda: self._process_payment("Stripe"),
                                         bd=0)
                    stripe_btn.image = stripe_img  # Keep reference to prevent garbage collection
                    stripe_btn.pack(pady=10)
            except Exception as e:
                logging.error(f"Error loading Stripe image: {e}")
                # Fallback to text button
                stripe_btn = tk.Button(self.payment_popup, 
                                     text="Pay with Stripe", 
                                     font=("Arial", 16), 
                                     command=lambda: self._process_payment("Stripe"),
                                     bg="#6772E5", fg="white",
                                     height=2, width=20)
                stripe_btn.pack(pady=10)
    
        # Only create mobile payment frame if at least one mobile option is enabled
        if settings["payment_options"]["venmo_enabled"] or settings["payment_options"]["cashapp_enabled"]:
            # Frame for Venmo and Cash App buttons (side by side)
            mobile_frame = tk.Frame(self.payment_popup, bg="white")
            mobile_frame.pack(pady=10)
    
            # Venmo button
            if settings["payment_options"]["venmo_enabled"]:
                venmo_path = payment_images_dir / "Venmo.png"
                if venmo_path.exists():
                    try:
                        with Image.open(venmo_path) as img:
                            # Resize to appropriate size
                            img = img.resize((200, 80), Image.LANCZOS)
                            venmo_img = ImageTk.PhotoImage(img)
                        
                            # Create button with image
                            venmo_btn = tk.Button(mobile_frame, 
                                                image=venmo_img, 
                                                command=lambda: self._process_payment("Venmo"),
                                                bd=0)
                            venmo_btn.image = venmo_img  # Keep reference
                            venmo_btn.pack(side=tk.LEFT, padx=10)
                    except Exception as e:
                        logging.error(f"Error loading Venmo image: {e}")
                        # Fallback to text button
                        venmo_btn = tk.Button(mobile_frame, 
                                            text="Venmo", 
                                            font=("Arial", 16), 
                                            command=lambda: self._process_payment("Venmo"),
                                            bg="#3D95CE", fg="white",
                                            height=2, width=10)
                        venmo_btn.pack(side=tk.LEFT, padx=10)
    
            # Cash App button
            if settings["payment_options"]["cashapp_enabled"]:
                cashapp_path = payment_images_dir / "cashapp.png"
                if cashapp_path.exists():
                    try:
                        with Image.open(cashapp_path) as img:
                            # Resize to same size as Venmo button
                            img = img.resize((200, 80), Image.LANCZOS)
                            cashapp_img = ImageTk.PhotoImage(img)
                        
                            # Create button with image - call the dedicated Cash App method directly
                            cashapp_btn = tk.Button(mobile_frame, 
                                                  image=cashapp_img, 
                                                  command=lambda: self._process_cashapp_payment(total),
                                                  bd=0)
                            cashapp_btn.image = cashapp_img  # Keep reference
                            cashapp_btn.pack(side=tk.LEFT, padx=10)
                    except Exception as e:
                        logging.error(f"Error loading Cash App image: {e}")
                        # Fallback to text button
                        cashapp_btn = tk.Button(mobile_frame, 
                                              text="Cash App", 
                                              font=("Arial", 16), 
                                              command=lambda: self._process_cashapp_payment(total),
                                              bg="#00D632", fg="white",
                                              height=2, width=10)
                        cashapp_btn.pack(side=tk.LEFT, padx=10)
    
        # Button frame for Return and Cancel buttons
        button_frame = tk.Frame(self.payment_popup, bg="white")
        button_frame.pack(pady=(30, 20), fill=tk.X, padx=20)
    
        # Return to Cart button
        return_btn = tk.Button(button_frame, 
                             text="Return to Cart", 
                             font=("Arial", 16), 
                             command=self._close_payment_popup,
                             bg="#3498db", fg="white",
                             height=2)
        return_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
    
        # Cancel Order button
        cancel_btn = tk.Button(button_frame, 
                             text="Cancel Order", 
                             font=("Arial", 16), 
                             command=self._cancel_from_payment,
                             bg="#e74c3c", fg="white",
                             height=2)
        cancel_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
    
        # Start timeout for payment popup
        self._start_payment_timeout()


    def _close_payment_popup(self):
        """Close the payment popup."""
        self._close_all_payment_popups()

    def _cancel_from_payment(self):
        """Cancel order from payment popup."""
        from tkinter import messagebox
        logging.info("Cancel from payment initiated")
    
        if messagebox.askyesno("Cancel Order", "Are you sure you want to cancel this order?"):
            logging.info("User confirmed order cancellation from payment popup")
            self._close_all_payment_popups()
            self._log_cancelled_cart("Customer")
            if hasattr(self, "on_exit"):
                self.on_exit()
        else:
            logging.info("User declined order cancellation from payment popup")

    def _process_payment(self, method):
        """Process payment with selected method."""
        # Debug logging
        logging.info(f"_process_payment called with method: {method}")
        
        # Use the pre-calculated total from _pay_now()
        if not hasattr(self, 'final_total'):
            logging.error("final_total not set, cannot process payment.")
            return

        # Get the final total
        total = self.final_total
        
        # Log the payment attempt with the correct total
        logging.info(f"Processing payment of ${total:.2f} with {method}")

        # Store the payment method for receipt printing
        if method == "Stripe":
            self.current_payment_method = "Credit Card"
        else:
            self.current_payment_method = method
        
        # Route to the correct QR code generation method
        if method == "Venmo":
            # Show QR code for Venmo payment with the calculated total
            self._show_venmo_qr_code(total)
        elif method == "Stripe":
            # Show QR code for Stripe payment with the calculated total
            self._show_stripe_qr_code(total)
        elif method == "Cash App":
            # This is usually called directly, but handle it here for consistency
            self._process_cashapp_payment(total)
        else:
            # Fallback for other/unknown payment methods
            logging.warning(f"Unknown payment method '{method}' called in _process_payment.")
            self._close_payment_popup()
            self._log_successful_transaction(self.current_payment_method, total)
            self._show_thank_you_popup()





#***CashApp***
    
    def _process_cashapp_payment(self, total):
        """Process Cash App payment with QR code."""
        logging.info(f"Processing Cash App payment for ${total:.2f}")

        # Set payment method for receipt printing - explicitly set to CashApp
        self.current_payment_method = "CashApp"
        logging.info(f"Set payment method to: {self.current_payment_method}")
        
        # Close the current payment popup
        if hasattr(self, 'payment_popup') and self.payment_popup:
            self.payment_popup.destroy()
        
        # Create a new popup for the QR code
        self.payment_popup = tk.Frame(self.root, bg="white", bd=3, relief=tk.RAISED)
        self.payment_popup.place(relx=0.5, rely=0.5, width=600, height=700, anchor=tk.CENTER)
        
        # Title
        title_label = tk.Label(self.payment_popup, 
                             text="Pay with Cash App", 
                             font=("Arial", 24, "bold"), 
                             bg="white")
        title_label.pack(pady=(20, 10))
        
        try:
            # Generate QR code and get transaction ID
            qr_img, transaction_id = self._generate_cashapp_qr_code(total)
            
            # Store transaction ID for reference
            self.current_transaction_id = transaction_id
            
            # Amount and transaction ID
            details_frame = tk.Frame(self.payment_popup, bg="white")
            details_frame.pack(pady=(0, 10))
            
            amount_label = tk.Label(details_frame, 
                                  text=f"Amount: ${total:.2f}", 
                                  font=("Arial", 18), 
                                  bg="white")
            amount_label.pack(pady=5)
            
            # Resize QR for display
            qr_img = qr_img.resize((300, 300), Image.LANCZOS)
            
            # Convert to PhotoImage
            qr_photo = ImageTk.PhotoImage(qr_img)
            
            # Display QR code
            qr_label = tk.Label(self.payment_popup, image=qr_photo, bg="white")
            qr_label.image = qr_photo  # Keep a reference
            qr_label.pack(pady=10)
            
            # Instructions
            instructions = (
                "1. Open your phone's camera app\n"
                "2. Scan this QR code\n"
                "3. Follow the link to the Cash App\n"
                "4. Complete payment in Cash App\n"
                "5. After payment, click 'Record Payment' below\n"
                "   and enter the last 4 digits of your transaction ID"
            )
            
            instructions_label = tk.Label(self.payment_popup, 
                                        text=instructions, 
                                        font=("Arial", 14), 
                                        bg="white",
                                        justify=tk.LEFT)
            instructions_label.pack(pady=10)
            
        except Exception as e:
            logging.error(f"Error generating Cash App QR code: {e}")
            import traceback
            logging.error(traceback.format_exc())
            
            # Show error message instead of QR code
            error_label = tk.Label(self.payment_popup, 
                                 text=f"Error generating QR code:\n{str(e)}", 
                                 font=("Arial", 16), 
                                 bg="white",
                                 fg="#e74c3c")  # Red color
            error_label.pack(pady=20)
        
        # Button frame
        button_frame = tk.Frame(self.payment_popup, bg="white")
        button_frame.pack(pady=(20, 20), fill=tk.X, padx=20)
        
        # Record Payment button
        record_btn = tk.Button(button_frame, 
                             text="Record Payment", 
                             font=("Arial", 16), 
                             command=self._show_transaction_id_entry,
                             bg="#27ae60", fg="white",
                             height=1)
        record_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Return to Cart button
        return_btn = tk.Button(button_frame, 
                             text="Return to Cart", 
                             font=("Arial", 16), 
                             command=self._close_payment_popup,
                             bg="#3498db", fg="white",
                             height=1)
        return_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Cancel Order button
        cancel_btn = tk.Button(button_frame, 
                             text="Cancel Order", 
                             font=("Arial", 16), 
                             command=self._cancel_from_payment,
                             bg="#e74c3c", fg="white",
                             height=1)
        cancel_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Start timeout for payment popup - 60 seconds
        self._start_payment_timeout(timeout_seconds=60)

    def _generate_cashapp_qr_code(self, total):
        """Generate a Cash App QR code for payment."""
        import qrcode
        import urllib.parse
        
        # Generate a unique transaction ID
        if not hasattr(self, 'current_transaction_id'):
            self.current_transaction_id = self._generate_transaction_id()
        
        # Format the amount with 2 decimal places
        formatted_total = "{:.2f}".format(total)
        
        # Get Cash App username
        cashapp_username = self.get_cashapp_username()

        # Create a detailed note with machine ID and transaction ID
        note = f"Payment #{self.current_transaction_id} - Machine: {self.machine_id}"    
        
        # Create a detailed note with machine ID and transaction ID
        note = f"Payment #{self.current_transaction_id} - Machine: {self.machine_id}"
        
        # Create the Cash App URL - use URL encoding for the note
        encoded_note = urllib.parse.quote(note)
        
        # Cash App uses $ prefix for cashtags
        if not cashapp_username.startswith('$'):
            cashapp_username = f"${cashapp_username}"
        
        # Create Cash App URL
        cashapp_url = f"https://cash.app/{cashapp_username}/{formatted_total}"
        
        # Add note as a parameter if supported
        cashapp_url += f"?note={encoded_note}"
        
        logging.info(f"Generated Cash App payment URL: {cashapp_url}")
        
        # Create QR code for the Cash App URL
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(cashapp_url)
        qr.make(fit=True)
        
        # Create an image from the QR Code
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Return the PIL Image and transaction ID
        return img, self.current_transaction_id

    def get_cashapp_username(self):
        """Get Cash App username from CashAppName.txt."""
        cashapp_user_path = Path.home() / "SelfCheck" / "Cred" / "CashAppName.txt"
        
        if not cashapp_user_path.exists():
            logging.error("CashAppName.txt not found")
            return "YourCashAppName"  # Default fallback
        
        try:
            with open(cashapp_user_path, 'r') as f:
                username = f.read().strip()
                if username:
                    return username
                else:
                    logging.error("CashAppName.txt is empty")
                    return "YourCashAppName"  # Default fallback
        except IOError as e:
            logging.error(f"Error reading CashAppName.txt: {e}")
            return "YourCashAppName"  # Default fallback

    #***Stripe***
    def _show_stripe_qr_code(self, total):
        """Show QR code for Stripe credit card payment."""
        # Close the current payment popup
        if hasattr(self, 'payment_popup') and self.payment_popup:
            self.payment_popup.destroy()
        
        # Create a new popup for the QR code
        self.payment_popup = tk.Frame(self.root, bg="white", bd=3, relief=tk.RAISED)
        self.payment_popup.place(relx=0.5, rely=0.5, width=600, height=700, anchor=tk.CENTER)
        
        # Title
        title_label = tk.Label(self.payment_popup, 
                             text="Pay with Credit Card", 
                             font=("Arial", 24, "bold"), 
                             bg="white")
        title_label.pack(pady=(20, 10))
        
        try:
            # Generate QR code and get session ID - pass the exact total
            qr_img, session_id = self._generate_stripe_qr_code(total)
            
            # Store session ID for reference
            self.current_stripe_session_id = session_id
            
            # Amount
            details_frame = tk.Frame(self.payment_popup, bg="white")
            details_frame.pack(pady=(0, 10))
            
            amount_label = tk.Label(details_frame, 
                                  text=f"Amount: ${total:.2f}", 
                                  font=("Arial", 18), 
                                  bg="white")
            amount_label.pack(pady=5)
            
            # Resize QR for display
            qr_img = qr_img.resize((300, 300), Image.LANCZOS)
            
            # Convert to PhotoImage
            qr_photo = ImageTk.PhotoImage(qr_img)
            
            # Display QR code
            qr_label = tk.Label(self.payment_popup, image=qr_photo, bg="white")
            qr_label.image = qr_photo  # Keep a reference
            qr_label.pack(pady=10)
            
            # Instructions
            instructions = (
                "1. Open your phone's camera app\n"
                "2. Scan this QR code\n"
                "3. Follow the link to the payment page\n"
                "4. Complete payment on your phone\n"
                "5. Wait for confirmation (automatic)"
            )
            
            instructions_label = tk.Label(self.payment_popup, 
                                        text=instructions, 
                                        font=("Arial", 14), 
                                        bg="white",
                                        justify=tk.LEFT)
            instructions_label.pack(pady=10)
            
            # Status message (initially empty)
            self.stripe_status_label = tk.Label(self.payment_popup,
                                              text="Waiting for payment...",
                                              font=("Arial", 14, "italic"),
                                              bg="white",
                                              fg="#888888")
            self.stripe_status_label.pack(pady=5)
            
        except Exception as e:
            logging.error(f"Error generating Stripe QR code: {e}")
            import traceback
            logging.error(traceback.format_exc())
            
            # Show error message instead of QR code
            error_label = tk.Label(self.payment_popup, 
                                 text=f"Error generating QR code:\n{str(e)}", 
                                 font=("Arial", 16), 
                                 bg="white",
                                 fg="#e74c3c")  # Red color
            error_label.pack(pady=20)
        
        # Button frame
        button_frame = tk.Frame(self.payment_popup, bg="white")
        button_frame.pack(pady=(20, 20), fill=tk.X, padx=20)
        
        # Return to Cart button
        return_btn = tk.Button(button_frame, 
                             text="Return to Cart", 
                             font=("Arial", 16), 
                             command=self._close_payment_popup,
                             bg="#3498db", fg="white",
                             height=1)
        return_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Cancel Order button
        cancel_btn = tk.Button(button_frame, 
                             text="Cancel Order", 
                             font=("Arial", 16), 
                             command=self._cancel_from_payment,
                             bg="#e74c3c", fg="white",
                             height=1)
        cancel_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Start polling for payment status
        self._start_payment_status_polling()
        
        # Start timeout for payment popup - 60 seconds
        self._start_stripe_payment_timeout()



    def _start_payment_status_polling(self):
        """Start polling for payment status with a 90-second timeout."""
        self.payment_polling_active = True
        self.payment_polling_start_time = time.time()
        self.payment_polling_timeout = 90  # 90 seconds total timeout
        self.confirmation_popup_shown = False
        self._check_payment_status()
        
    def _check_payment_status(self):
        """Check if payment has been completed with timeout handling."""
        # Stop if polling is no longer active
        if not hasattr(self, 'payment_polling_active') or not self.payment_polling_active:
            return
            
        # Calculate elapsed time
        elapsed_time = time.time() - self.payment_polling_start_time
        remaining_time = self.payment_polling_timeout - elapsed_time
        
        # Check if we've exceeded the timeout
        if remaining_time <= 0:
            logging.info("Payment polling timeout reached (90 seconds)")
            self._payment_polling_timeout()
            return
            
        # Show confirmation popup in the last 30 seconds if not already shown
        if remaining_time <= 30 and not self.confirmation_popup_shown:
            self._show_payment_confirmation_popup()
            self.confirmation_popup_shown = True
            
        # Poll Stripe for payment status
        try:
            if hasattr(self, 'current_stripe_session_id'):
                logging.info(f"Checking payment status for session: {self.current_stripe_session_id}")
                session = stripe.checkout.Session.retrieve(self.current_stripe_session_id)
                logging.info(f"Payment status: {session.payment_status}")
                
                if session.payment_status == 'paid':
                    logging.info("Payment confirmed via polling!")
                    self._on_stripe_payment_received()
                    return
                    
            # Schedule next check in 2 seconds
            self.payment_check_timer = self.root.after(2000, self._check_payment_status)
        except Exception as e:
            logging.error(f"Error checking payment status: {e}")
            # Continue polling despite errors
            self.payment_check_timer = self.root.after(5000, self._check_payment_status)
            
    def _payment_polling_timeout(self):
        """Handle timeout for payment polling."""
        logging.info("Payment polling timed out")
        self.payment_polling_active = False
        
        # Calculate the total
        subtotal = sum(item["price"] * item["qty"] for item in self.cart_items.values())
        taxable_subtotal = sum(
            item["price"] * item["qty"] 
            for item in self.cart_items.values() if item["taxable"]
        )
        tax_amount = taxable_subtotal * (self.tax_rate / 100)
        total = subtotal + tax_amount
        
        # Log the unconfirmed payment
        self._log_unconfirmed_stripe_payment(total)
        
        # Close all popups
        self._close_all_payment_popups()
        
        # Clear cart and return to idle mode
        self.cart_items = {}
        if hasattr(self, "on_exit"):
            self.on_exit()
            
    def _show_payment_confirmation_popup(self):
        """Show confirmation popup for Stripe payment."""
        # Create popup
        self.stripe_confirm_popup = tk.Frame(self.root, bg="white", bd=3, relief=tk.RAISED)
        self.stripe_confirm_popup.place(relx=0.5, rely=0.5, width=500, height=300, anchor=tk.CENTER)
        
        # Message - Updated as requested
        message = tk.Label(self.stripe_confirm_popup, 
                         text="Please confirm you submitted your payment on your phone", 
                         font=("Arial", 20, "bold"), bg="white", wraplength=450)
        message.pack(pady=(40, 20))
        
        # Countdown
        self.stripe_countdown_value = 30
        self.stripe_countdown_label = tk.Label(self.stripe_confirm_popup, 
                                             text=f"Returning to main menu in {self.stripe_countdown_value} seconds", 
                                             font=("Arial", 18), bg="white")
        self.stripe_countdown_label.pack(pady=20)
        
        # Start countdown
        self._update_stripe_countdown()
        
    def _update_stripe_countdown(self):
        """Update the Stripe confirmation countdown timer."""
        # Check if payment was received
        if not hasattr(self, 'payment_polling_active') or not self.payment_polling_active:
            if hasattr(self, 'stripe_confirm_popup') and self.stripe_confirm_popup:
                self.stripe_confirm_popup.destroy()
            return
        
        # Update countdown
        self.stripe_countdown_value -= 1
        if hasattr(self, 'stripe_countdown_label') and self.stripe_countdown_label:
            self.stripe_countdown_label.config(text=f"Returning to main menu in {self.stripe_countdown_value} seconds")
        
        if self.stripe_countdown_value <= 0:
            self._payment_polling_timeout()
            return
            
        self.stripe_countdown_after = self.root.after(1000, self._update_stripe_countdown)





    def _generate_stripe_qr_code(self, total):
        """Generate a Stripe payment QR code."""
        import qrcode
        import stripe
        import json
        import uuid
        
        # Log the total being used
        logging.info(f"Generating Stripe QR code with total: ${total:.2f}")
        
        # Load Stripe credentials
        try:
            stripe_secret_key_path = Path.home() / "SelfCheck" / "Cred" / "Stripe_Secret_Key.txt"
            stripe_url_path = Path.home() / "SelfCheck" / "Cred" / "Stripe_URL.txt"
            
            if not stripe_secret_key_path.exists():
                raise FileNotFoundError(f"Stripe secret key file not found: {stripe_secret_key_path}")
            
            # Read credentials
            with open(stripe_secret_key_path, 'r') as f:
                stripe_secret_key = f.read().strip()
            
            # Initialize Stripe
            stripe.api_key = stripe_secret_key
            
            # Format the amount with 2 decimal places and convert to cents
            price_val = int(float(total) * 100)
            
            # Generate a unique reference ID
            reference_id = str(uuid.uuid4())
            
            # Store the reference ID for verification
            self.stripe_reference_id = reference_id
            
            # Get success and cancel URLs
            success_url = "https://www.vendlasvegas.com/thanks"
            cancel_url = "https://www.vendlasvegas.com/thanks"
            
            # Try to read from URL file if it exists
            if stripe_url_path.exists():
                try:
                    with open(stripe_url_path, 'r') as f:
                        base_url = f.read().strip()
                        if base_url:
                            success_url = f"{base_url}/success"
                            cancel_url = f"{base_url}/cancel"
                except Exception as e:
                    logging.error(f"Error reading Stripe URL: {e}")
            
            # Create a Stripe Checkout Session - using the simpler format from your working code
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": price_val,
                        "product_data": {
                            "name": f"Purchase from {self.machine_id}"
                        }
                    },
                    "quantity": 1
                }],
                mode="payment",
                metadata={
                    "machine_id": self.machine_id,
                    "transaction_id": self.transaction_id,
                    "reference_id": reference_id
                },
                success_url=success_url,
                cancel_url=cancel_url
            )
            
            # Get the session ID
            session_id = checkout_session.id
            
            # Create the URL for the QR code
            checkout_url = checkout_session.url
            
            logging.info(f"Generated Stripe checkout URL: {checkout_url}")
            logging.info(f"Stripe session ID: {session_id}")
            
            # Create QR code for the checkout URL
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(checkout_url)
            qr.make(fit=True)
            
            # Create an image from the QR Code
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Return the PIL Image and session ID
            return img, session_id
            
        except Exception as e:
            logging.error(f"Error generating Stripe QR code: {e}")
            import traceback
            logging.error(traceback.format_exc())
            raise


# Check 
    def _start_stripe_webhook_listener(self):
        """Start listening for Stripe webhook events."""
        import threading
        import http.server
        import socketserver
        import json
        import stripe
        import time
        from datetime import datetime, timedelta
        
        # Load webhook secret
        try:
            webhook_secret_path = Path.home() / "SelfCheck" / "Cred" / "Stripe_Webhook_Secret.txt"
            
            if not webhook_secret_path.exists():
                logging.warning(f"Stripe webhook secret file not found: {webhook_secret_path}")
                logging.warning("Webhook verification will be disabled")
                webhook_secret = None
            else:
                with open(webhook_secret_path, 'r') as f:
                    webhook_secret = f.read().strip()
            
            # Store the start time for timeout checking
            self.stripe_webhook_start_time = time.time()
            
            # Flag to track if payment was received
            self.stripe_payment_received = False
            
            # Define webhook handler
            class StripeWebhookHandler(http.server.BaseHTTPRequestHandler):
                def do_POST(self):
                    content_length = int(self.headers['Content-Length'])
                    post_data = self.rfile.read(content_length)
                    
                    try:
                        # Parse the JSON payload
                        event_json = json.loads(post_data)
                        
                        # Verify webhook signature if secret is available
                        if webhook_secret:
                            try:
                                event = stripe.Webhook.construct_event(
                                    post_data, self.headers['Stripe-Signature'], webhook_secret
                                )
                            except Exception as e:
                                logging.error(f"Webhook signature verification failed: {e}")
                                self.send_response(400)
                                self.end_headers()
                                self.wfile.write(b'Webhook signature verification failed')
                                return
                        else:
                            # If no webhook secret, just use the parsed JSON
                            event = event_json
                        
                        # Log the event
                        logging.info(f"Received Stripe webhook event: {event.get('type')}")
                        
                        # Check if it's a payment success event
                        if event.get('type') == 'checkout.session.completed':
                            session = event.get('data', {}).get('object', {})
                            
                            # Get metadata
                            metadata = session.get('metadata', {})
                            machine_id = metadata.get('machine_id')
                            
                            # Check if this webhook is for this machine
                            if machine_id == self.server.machine_id:
                                logging.info(f"Valid payment confirmation received for machine {machine_id}")
                                
                                # Set payment received flag
                                self.server.payment_received = True
                                
                                # Schedule UI update in main thread
                                self.server.root.after(0, self.server.payment_callback)
                            else:
                                logging.info(f"Webhook for different machine: {machine_id}")
                        
                        # Send response
                        self.send_response(200)
                        self.end_headers()
                        self.wfile.write(b'Event received')
                        
                    except Exception as e:
                        logging.error(f"Error processing webhook: {e}")
                        self.send_response(400)
                        self.end_headers()
                        self.wfile.write(b'Webhook error')
            
            # Create server
            class StripeWebhookServer(socketserver.TCPServer):
                def __init__(self, server_address, RequestHandlerClass, machine_id, root, payment_callback):
                    self.machine_id = machine_id
                    self.root = root
                    self.payment_callback = payment_callback
                    self.payment_received = False
                    socketserver.TCPServer.__init__(self, server_address, RequestHandlerClass)
            
            # Start server in a separate thread
            def run_server():
                try:
                    # Use a random available port
                    with StripeWebhookServer(('localhost', 0), StripeWebhookHandler, 
                                            self.machine_id, 
                                            self.root, self._on_stripe_payment_received) as httpd:
                        
                        # Store the server port
                        self.stripe_webhook_port = httpd.server_address[1]
                        logging.info(f"Stripe webhook server started on port {self.stripe_webhook_port}")
                        
                        # Serve until shutdown
                        httpd.serve_forever()
                except Exception as e:
                    logging.error(f"Error in webhook server: {e}")
            
            # Start server thread
            self.stripe_webhook_thread = threading.Thread(target=run_server)
            self.stripe_webhook_thread.daemon = True
            self.stripe_webhook_thread.start()
            
        except Exception as e:
            logging.error(f"Error starting Stripe webhook listener: {e}")
            import traceback
            logging.error(traceback.format_exc())


    def _on_stripe_payment_received(self):
        """Handle successful Stripe payment."""
        logging.info("Stripe payment received and verified")
        
        # Stop polling
        self.payment_polling_active = False
        if hasattr(self, 'payment_check_timer') and self.payment_check_timer:
            self.root.after_cancel(self.payment_check_timer)
            self.payment_check_timer = None
            
        # Close confirmation popup if it exists
        if hasattr(self, 'stripe_confirm_popup') and self.stripe_confirm_popup:
            self.stripe_confirm_popup.destroy()
            self.stripe_confirm_popup = None
            
        # Cancel countdown timer if it exists
        if hasattr(self, 'stripe_countdown_after') and self.stripe_countdown_after:
            self.root.after_cancel(self.stripe_countdown_after)
            self.stripe_countdown_after = None
        
        # Update status label if it exists
        if hasattr(self, 'stripe_status_label') and self.stripe_status_label:
            self.stripe_status_label.config(text="Payment confirmed! Processing...", fg="#27ae60")
        
        # ... rest of your existing code ...

        
        # Set payment received flag
        self.stripe_payment_received = True
        
        # Calculate the total for logging
        subtotal = sum(item["price"] * item["qty"] for item in self.cart_items.values())
        taxable_subtotal = sum(
            item["price"] * item["qty"] 
            for item in self.cart_items.values() if item["taxable"]
        )
        tax_amount = taxable_subtotal * (self.tax_rate / 100)
        total = subtotal + tax_amount
        
        # Store the payment method for receipt printing
        self.current_payment_method = "Credit Card"
        
        # Log the transaction
        self._log_successful_transaction("Credit Card", total)
        
        # Wait a moment to show the confirmation message
        self.root.after(2000, self._show_thank_you_popup)


    def _start_stripe_payment_timeout(self):
        """Start timeout for Stripe payment."""
        self.stripe_payment_timeout = self.root.after(60000, self._stripe_payment_timeout)

    def _stripe_payment_timeout(self):
        """Handle timeout for Stripe payment."""
        # Check if payment was received
        if hasattr(self, 'stripe_payment_received') and self.stripe_payment_received:
            return
        
        # Show confirmation popup
        self._show_stripe_confirmation_popup()

    def _show_stripe_confirmation_popup(self):
        """Show confirmation popup for Stripe payment."""
        # Create popup
        self.stripe_confirm_popup = tk.Frame(self.root, bg="white", bd=3, relief=tk.RAISED)
        self.stripe_confirm_popup.place(relx=0.5, rely=0.5, width=500, height=300, anchor=tk.CENTER)
        
        # Message
        message = tk.Label(self.stripe_confirm_popup, text="Please Confirm your Payment was submitted on your phone", 
                         font=("Arial", 20, "bold"), bg="white", wraplength=450)
        message.pack(pady=(40, 20))
        
        # Countdown
        self.stripe_countdown_value = 30
        self.stripe_countdown_label = tk.Label(self.stripe_confirm_popup, 
                                             text=f"Returning to main menu in {self.stripe_countdown_value} seconds", 
                                             font=("Arial", 18), bg="white")
        self.stripe_countdown_label.pack(pady=20)
        
        # Start countdown
        self._update_stripe_countdown()

    def _update_stripe_countdown(self):
        """Update the Stripe confirmation countdown timer."""
        # Check if payment was received
        if hasattr(self, 'stripe_payment_received') and self.stripe_payment_received:
            if hasattr(self, 'stripe_confirm_popup') and self.stripe_confirm_popup:
                self.stripe_confirm_popup.destroy()
            return
        
        # Update countdown
        self.stripe_countdown_value -= 1
        self.stripe_countdown_label.config(text=f"Returning to main menu in {self.stripe_countdown_value} seconds")
        
        if self.stripe_countdown_value <= 0:
            self._stripe_confirmation_expired()
            return
            
        self.stripe_countdown_after = self.root.after(1000, self._update_stripe_countdown)

    def _stripe_confirmation_expired(self):
        """Handle expiration of Stripe confirmation popup."""
        # Calculate the total
        subtotal = sum(item["price"] * item["qty"] for item in self.cart_items.values())
        taxable_subtotal = sum(
            item["price"] * item["qty"] 
            for item in self.cart_items.values() if item["taxable"]
        )
        tax_amount = taxable_subtotal * (self.tax_rate / 100)
        total = subtotal + tax_amount
        
        # Log the unconfirmed payment
        self._log_unconfirmed_stripe_payment(total)
        
        # Close all popups
        self._close_all_payment_popups()
        
        # Clear cart and return to idle mode
        self.cart_items = {}
        if hasattr(self, "on_exit"):
            self.on_exit()

    def _log_unconfirmed_stripe_payment(self, total):
        """Log an unconfirmed Stripe payment to the Service tab."""
        try:
            # Use more comprehensive scopes
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_file(str(GS_CRED_PATH), scopes=scopes)
            gc = gspread.authorize(creds)
            
            # Open the spreadsheet and worksheet
            sheet = gc.open(GS_SHEET_NAME).worksheet("Service")
            
            # Prepare row data
            timestamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
            user = self.machine_id
            action = f"CC Payment not confirmed - ${total:.2f}"
            
            # Create row with the correct format
            row = [timestamp, user, action]
            
            # Log locally first
            logging.info(f"Logging unconfirmed payment: {timestamp}, {user}, {action}")
            
            try:
                # Try to append to sheet
                sheet.append_row(row)
                logging.info(f"Successfully logged unconfirmed payment to Service tab")
            except Exception as api_error:
                logging.error(f"Error logging to Service tab: {api_error}")
                # Create a local log file as fallback
                log_dir = Path.home() / "SelfCheck" / "Logs"
                log_dir.mkdir(parents=True, exist_ok=True)
                log_file = log_dir / "transaction_log.csv"
                
                # Append to local log file
                with open(log_file, 'a') as f:
                    f.write(f"{timestamp},{user},{action}\n")
                logging.info(f"Logged unconfirmed payment to local file instead: {log_file}")
                
        except Exception as e:
            logging.error(f"Failed to log unconfirmed payment: {e}")
            import traceback
            logging.error(traceback.format_exc())

    

    def _show_venmo_qr_code(self, total):
        """Show QR code for Venmo payment."""
        # Close the current payment popup
        if hasattr(self, 'payment_popup') and self.payment_popup:
            self.payment_popup.destroy()
        
        # Create a new popup for the QR code
        self.payment_popup = tk.Frame(self.root, bg="white", bd=3, relief=tk.RAISED)
        self.payment_popup.place(relx=0.5, rely=0.5, width=600, height=700, anchor=tk.CENTER)
        
        # Title
        title_label = tk.Label(self.payment_popup, 
                             text="Pay with Venmo", 
                             font=("Arial", 24, "bold"), 
                             bg="white")
        title_label.pack(pady=(20, 10))
        
        try:
            # Generate QR code and get transaction ID - pass the exact total
            qr_img, transaction_id = self._generate_venmo_qr_code(total)
            
            # Store transaction ID for reference
            self.current_transaction_id = transaction_id
            
            # Amount and transaction ID
            details_frame = tk.Frame(self.payment_popup, bg="white")
            details_frame.pack(pady=(0, 10))
            
            amount_label = tk.Label(details_frame, 
                                  text=f"Amount: ${total:.2f}", 
                                  font=("Arial", 18), 
                                  bg="white")
            amount_label.pack(pady=5)
            
            # Resize QR for display
            qr_img = qr_img.resize((300, 300), Image.LANCZOS)
            
            # Convert to PhotoImage
            qr_photo = ImageTk.PhotoImage(qr_img)
            
            # Display QR code
            qr_label = tk.Label(self.payment_popup, image=qr_photo, bg="white")
            qr_label.image = qr_photo  # Keep a reference
            qr_label.pack(pady=10)
            
            # Instructions
            instructions = (
                "1. Open your phone's camera app\n"
                "2. Scan this QR code\n"
                "3. Follow the link to the Venmo app\n"
                "4. Complete payment in the Venmo app\n"
                "5. After payment, click 'Record Payment' below\n"
                "   and enter the last 4 digits of your transaction ID"
            )
            
            instructions_label = tk.Label(self.payment_popup, 
                                        text=instructions, 
                                        font=("Arial", 14), 
                                        bg="white",
                                        justify=tk.LEFT)
            instructions_label.pack(pady=10)
            
        except Exception as e:
            logging.error(f"Error generating Venmo QR code: {e}")
            import traceback
            logging.error(traceback.format_exc())
            
            # Show error message instead of QR code
            error_label = tk.Label(self.payment_popup, 
                                 text=f"Error generating QR code:\n{str(e)}", 
                                 font=("Arial", 16), 
                                 bg="white",
                                 fg="#e74c3c")  # Red color
            error_label.pack(pady=20)
        
        # Button frame
        button_frame = tk.Frame(self.payment_popup, bg="white")
        button_frame.pack(pady=(20, 20), fill=tk.X, padx=20)
        
        # Record Payment button
        record_btn = tk.Button(button_frame, 
                             text="Record Payment", 
                             font=("Arial", 16), 
                             command=self._show_transaction_id_entry,
                             bg="#27ae60", fg="white",
                             height=1)
        record_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Return to Cart button
        return_btn = tk.Button(button_frame, 
                             text="Return to Cart", 
                             font=("Arial", 16), 
                             command=self._close_payment_popup,
                             bg="#3498db", fg="white",
                             height=1)
        return_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Cancel Order button
        cancel_btn = tk.Button(button_frame, 
                             text="Cancel Order", 
                             font=("Arial", 16), 
                             command=self._cancel_from_payment,
                             bg="#e74c3c", fg="white",
                             height=1)
        cancel_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Start timeout for payment popup - 60 seconds
        self._start_payment_timeout(timeout_seconds=60)


    def _generate_venmo_qr_code(self, total):
        """Generate a Venmo QR code for payment."""
        import qrcode
        import urllib.parse
        
        # Log the total being used
        logging.info(f"Generating Venmo QR code with total: ${total:.2f}")
        
        # Generate a unique transaction ID
        if not hasattr(self, 'current_transaction_id'):
            self.current_transaction_id = self._generate_transaction_id()
        
        # Format the amount with 2 decimal places
        formatted_total = "{:.2f}".format(total)
        
        # Get Venmo username
        venmo_username = self.get_venmo_username()
        
        # Create a detailed note with machine ID and transaction ID
        note = f"Payment #{self.current_transaction_id} - Machine: {self.machine_id}"
        
        # Create the Venmo URL - use URL encoding for the note
        encoded_note = urllib.parse.quote(note)
        
        venmo_url = f"venmo://paycharge?txn=pay&recipients={venmo_username}&amount={formatted_total}&note={encoded_note}"
        
        # Also create a web URL for devices that don't have Venmo app
        web_url = f"https://venmo.com/{venmo_username}?txn=pay&amount={formatted_total}&note={encoded_note}"
        
        logging.info(f"Generated Venmo payment URL: {venmo_url}")
        logging.info(f"Generated Venmo web URL: {web_url}")
        
        # Create QR code for the Venmo URL
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(venmo_url)
        qr.make(fit=True)
        
        # Create an image from the QR Code
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Return the PIL Image and transaction ID
        return img, self.current_transaction_id



    def get_venmo_username(self):
        """Get Venmo username from VenmoUser.txt."""
        venmo_user_path = Path.home() / "SelfCheck" / "Cred" / "VenmoUser.txt"
        
        if not venmo_user_path.exists():
            logging.error("VenmoUser.txt not found")
            return "YourVenmoUsername"  # Default fallback
        
        try:
            with open(venmo_user_path, 'r') as f:
                username = f.read().strip()
                if username:
                    return username
                else:
                    logging.error("VenmoUser.txt is empty")
                    return "YourVenmoUsername"  # Default fallback
        except IOError as e:
            logging.error(f"Error reading VenmoUser.txt: {e}")
            return "YourVenmoUsername"  # Default fallback

    def _show_transaction_id_entry(self):
        """Show transaction ID entry popup with number pad."""
        # Close any existing transaction ID entry popup
        if hasattr(self, 'transaction_id_popup') and self.transaction_id_popup:
            self.transaction_id_popup.destroy()
        
        # Create transaction ID entry popup
        self.transaction_id_popup = tk.Frame(self.root, bg="white", bd=3, relief=tk.RAISED)
        self.transaction_id_popup.place(relx=0.5, rely=0.5, width=500, height=600, anchor=tk.CENTER)
        
        # Title
        title_label = tk.Label(self.transaction_id_popup, 
                             text="Enter last 4 digits of Venmo/CashApp Transaction ID#", 
                             font=("Arial", 18, "bold"), 
                             bg="white",
                             wraplength=450)
        title_label.pack(pady=(20, 10))
        
        # Entry field
        self.transaction_id_var = tk.StringVar()
        entry_frame = tk.Frame(self.transaction_id_popup, bg="white")
        entry_frame.pack(pady=20)
        
        entry_field = tk.Entry(entry_frame, 
                             textvariable=self.transaction_id_var, 
                             font=("Arial", 24), 
                             width=6, 
                             justify=tk.CENTER)
        entry_field.pack(side=tk.LEFT, padx=10)
        entry_field.focus_set()  # Set focus to the entry field
        
        # Number pad frame
        numpad_frame = tk.Frame(self.transaction_id_popup, bg="white")
        numpad_frame.pack(pady=20)
        
        # Create number buttons
        buttons = [
            ['1', '2', '3'],
            ['4', '5', '6'],
            ['7', '8', '9'],
            ['Backspace', '0', 'Enter']
        ]
        
        for row_idx, row in enumerate(buttons):
            for col_idx, btn_text in enumerate(row):
                if btn_text == 'Backspace':
                    # Backspace button
                    btn = tk.Button(numpad_frame, 
                                  text=btn_text, 
                                  font=("Arial", 16), 
                                  bg="#e74c3c", fg="white",
                                  width=8, height=2,
                                  command=lambda: self._transaction_id_backspace())
                elif btn_text == 'Enter':
                    # Enter button
                    btn = tk.Button(numpad_frame, 
                                  text=btn_text, 
                                  font=("Arial", 16), 
                                  bg="#27ae60", fg="white",
                                  width=8, height=2,
                                  command=self._process_transaction_id)
                else:
                    # Number button
                    btn = tk.Button(numpad_frame, 
                                  text=btn_text, 
                                  font=("Arial", 20), 
                                  bg="#3498db", fg="white",
                                  width=4, height=2,
                                  command=lambda b=btn_text: self._transaction_id_add_digit(b))
                
                btn.grid(row=row_idx, column=col_idx, padx=5, pady=5)
        
        # Bind keyboard events
        self.root.bind("<Key>", self._transaction_id_key_press)
        
        # Start timeout - 60 seconds
        self.transaction_id_timeout = self.root.after(60000, self._transaction_id_timeout)
    
    def _transaction_id_add_digit(self, digit):
        """Add a digit to the transaction ID entry."""
        current = self.transaction_id_var.get()
        if len(current) < 4:  # Limit to 4 digits
            self.transaction_id_var.set(current + digit)
    
    def _transaction_id_backspace(self):
        """Remove the last digit from the transaction ID entry."""
        current = self.transaction_id_var.get()
        self.transaction_id_var.set(current[:-1])
    
    def _transaction_id_key_press(self, event):
        """Handle keyboard input for transaction ID entry."""
        if not hasattr(self, 'transaction_id_popup') or not self.transaction_id_popup:
            return
            
        if event.char.isdigit() and len(self.transaction_id_var.get()) < 4:
            # Add digit
            self.transaction_id_var.set(self.transaction_id_var.get() + event.char)
        elif event.keysym == 'BackSpace':
            # Backspace
            self._transaction_id_backspace()
        elif event.keysym == 'Return':
            # Enter
            self._process_transaction_id()
    
    def _transaction_id_timeout(self):
        """Handle timeout for transaction ID entry."""
        if hasattr(self, 'transaction_id_popup') and self.transaction_id_popup:
            self.transaction_id_popup.destroy()
            self.transaction_id_popup = None
            
        # Unbind keyboard events
        self.root.unbind("<Key>")
        self.root.bind("<Key>", self._on_key)  # Restore original key binding
        
        # Return to payment popup
        messagebox.showinfo("Timeout", "Transaction ID entry timed out.")
    
    def _process_transaction_id(self):
        """Process the entered transaction ID."""
        # Cancel timeout
        if hasattr(self, 'transaction_id_timeout') and self.transaction_id_timeout:
            self.root.after_cancel(self.transaction_id_timeout)
            self.transaction_id_timeout = None
        
        # Get entered ID
        entered_id = self.transaction_id_var.get().strip()
        
        # Log the entered ID
        logging.info(f"Transaction ID entered: {entered_id}")
        
        # Close transaction ID popup
        if hasattr(self, 'transaction_id_popup') and self.transaction_id_popup:
            self.transaction_id_popup.destroy()
            self.transaction_id_popup = None
        
        # Unbind keyboard events
        self.root.unbind("<Key>")
        self.root.bind("<Key>", self._on_key)  # Restore original key binding
        
        # Calculate the total for processing
        subtotal = sum(item["price"] * item["qty"] for item in self.cart_items.values())
        taxable_subtotal = sum(
            item["price"] * item["qty"] 
            for item in self.cart_items.values() if item["taxable"]
        )
        tax_amount = taxable_subtotal * (self.tax_rate / 100)
        total = subtotal + tax_amount
        
        # Log the current payment method for debugging
        logging.info(f"Current payment method before logging transaction: {self.current_payment_method}")
        
        # Log the transaction with the entered ID
        self._log_successful_transaction(self.current_payment_method, total, entered_id)
        
        # Show thank you popup
        self._show_thank_you_popup()


    def _show_thank_you_popup(self):
        """Show thank you popup with receipt options."""
        # Close any existing popups
        self._close_all_payment_popups()
        
        # Create thank you popup - make it larger to accommodate the additional button
        self.thank_you_popup = tk.Frame(self.root, bg="white", bd=3, relief=tk.RAISED)
        self.thank_you_popup.place(relx=0.5, rely=0.5, width=600, height=450, anchor=tk.CENTER)
        
        # Title
        title_label = tk.Label(self.thank_you_popup, 
                             text="Thank you for your payment", 
                             font=("Arial", 24, "bold"), 
                             bg="white")
        title_label.pack(pady=(40, 20))
        
        # Receipt text
        receipt_label = tk.Label(self.thank_you_popup, 
                               text="Would you like a receipt?", 
                               font=("Arial", 20), 
                               bg="white")
        receipt_label.pack(pady=(0, 30))
        
        # Load settings
        settings_path = Path.home() / "SelfCheck" / "Cred" / "Settings.json"
        try:
            with open(settings_path, 'r') as f:
                settings = json.load(f)
        except Exception as e:
            logging.error(f"Error loading settings: {e}")
            settings = {
                "payment_options": {
                    "venmo_enabled": True,
                    "cashapp_enabled": True
                },
                "receipt_options": {
                    "print_receipt_enabled": True
                }
            }
        
        # Button frame
        button_frame = tk.Frame(self.thank_you_popup, bg="white")
        button_frame.pack(pady=20, fill=tk.X, padx=40)
        
        # Top row frame
        top_row = tk.Frame(button_frame, bg="white")
        top_row.pack(fill=tk.X, pady=(0, 10))
        
        # Bottom row frame
        bottom_row = tk.Frame(button_frame, bg="white")
        bottom_row.pack(fill=tk.X)
        
        # Print button - only if enabled in settings
        if settings["receipt_options"]["print_receipt_enabled"]:
            print_btn = tk.Button(top_row, 
                                text="Print", 
                                font=("Arial", 18, "bold"), 
                                bg="#3498db", fg="white",
                                command=lambda: self._receipt_option_selected("print"),
                                width=8, height=2)
            print_btn.pack(side=tk.LEFT, padx=10, expand=True)
        
        # Email button (top right or center if print is disabled)
        email_btn = tk.Button(top_row, 
                            text="Email", 
                            font=("Arial", 18), 
                            bg="#2ecc71", fg="white",
                            command=lambda: self._receipt_option_selected("email"),
                            width=8, height=2)
        email_btn.pack(side=tk.LEFT, padx=10, expand=True)
        
        # Text receipt button (bottom left)
        text_btn = tk.Button(bottom_row, 
                           text="Text", 
                           font=("Arial", 18), 
                           bg="#9b59b6", fg="white",
                           command=lambda: self._receipt_option_selected("text"),
                           width=8, height=2)
        text_btn.pack(side=tk.LEFT, padx=10, expand=True)
        
        # None button (bottom right)
        none_btn = tk.Button(bottom_row, 
                           text="None", 
                           font=("Arial", 18), 
                           bg="#7f8c8d", fg="white",
                           command=self._thank_you_complete,
                           width=8, height=2)
        none_btn.pack(side=tk.LEFT, padx=10, expand=True)
        
        # Start timeout - 20 seconds
        self.thank_you_timeout = self.root.after(20000, self._thank_you_timeout)



    def _thank_you_timeout(self):
        """Handle timeout on the thank you screen."""
        logging.info("Thank you screen timed out")
        self._thank_you_complete()

    def _receipt_option_selected(self, option):
        """Handle receipt option selection."""
        logging.info(f"Receipt option selected: {option}")
        
        if option == "print":
            # Calculate the total
            subtotal = sum(item["price"] * item["qty"] for item in self.cart_items.values())
            taxable_subtotal = sum(
                item["price"] * item["qty"] 
                for item in self.cart_items.values() if item["taxable"]
            )
            tax_amount = taxable_subtotal * (self.tax_rate / 100)
            total = subtotal + tax_amount
            
            # Get payment method (default to "Unknown" if not set)
            payment_method = getattr(self, 'current_payment_method', "Unknown")
            
            # Try to print receipt
            success = self.print_receipt(payment_method, total)
            
            # Skip success popup and go directly to thank you complete
            self._thank_you_complete()
            
        elif option == "email":
            # Show email entry popup with virtual keyboard
            self._show_email_entry_popup()
            
        elif option == "text":
            # Show QR code for text message receipt
            self._show_receipt_qr()
            
        else:
            # Always complete the thank you process and return to idle mode
            self._thank_you_complete()
 


    def _log_transaction_details(self):
        """Log detailed transaction information to the Transactions tab in Google Sheet."""
        if not self.cart_items:
            logging.info("No items in cart to log transaction details")
            return
            
        logging.info("Logging transaction details to Transactions tab")
        
        try:
            # Connect to Google Sheet
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_file(str(GS_CRED_PATH), scopes=scopes)
            gc = gspread.authorize(creds)
            
            # Open the transactions sheet
            sheet = gc.open(GS_SHEET_NAME).worksheet("Transactions")
            
            # Calculate totals
            subtotal = sum(item["price"] * item["qty"] for item in self.cart_items.values())
            
            # Apply discount if any
            discount_amount = getattr(self, 'discount_amount', 0)
            discount_type = getattr(self, 'discount_type', None)
            discount_info = getattr(self, 'current_discount', None)
            
            # Adjust subtotal after discount
            adjusted_subtotal = subtotal - discount_amount
            
            # Ensure adjusted subtotal is not negative
            adjusted_subtotal = max(0, adjusted_subtotal)
            
            # Calculate tax
            taxable_subtotal = sum(
                item["price"] * item["qty"] 
                for item in self.cart_items.values() if item["taxable"]
            )
            
            # If we have a discount, adjust taxable subtotal proportionally
            if discount_amount > 0 and subtotal > 0:
                # For total discounts, reduce taxable amount proportionally
                if discount_type in ['dollar_total', 'percent_total']:
                    taxable_subtotal = max(0, taxable_subtotal * (adjusted_subtotal / subtotal))
                # For item-specific discounts, we need to check which items were discounted
                elif discount_type in ['dollar_items', 'percent_items'] and hasattr(self, 'discount_items'):
                    # Calculate tax reduction for discounted taxable items
                    tax_reduction = 0
                    for upc, item in self.cart_items.items():
                        if item["taxable"] and any(self._match_upc(upc, discount_upc) for discount_upc in self.discount_items):
                            if discount_type == 'dollar_items':
                                # Reduce by dollar amount per item, limited by item price
                                item_discount = min(float(discount_info.get('dollars', 0)), item["price"]) * item["qty"]
                                tax_reduction += item_discount
                            else:  # percent_items
                                # Reduce by percentage of item price
                                percent = float(discount_info.get('percent', 0))
                                item_discount = item["price"] * (percent / 100) * item["qty"]
                                tax_reduction += item_discount
                    
                    # Adjust taxable subtotal
                    taxable_subtotal = max(0, taxable_subtotal - tax_reduction)
            
            tax_amount = taxable_subtotal * (self.tax_rate / 100)
            total = adjusted_subtotal + tax_amount
            total_items = sum(item["qty"] for item in self.cart_items.values())
            
            # Get current date and time
            now = datetime.now()
            date_str = now.strftime("%m/%d/%Y")
            time_str = now.strftime("%H:%M:%S")
            
            # Prepare row data - KEEP ORIGINAL FORMAT
            row_data = [
                f"TXN-{self.transaction_id}",  # Transaction ID
                date_str,                      # Date
                time_str,                      # Time
                str(total_items),              # Items
                self.current_payment_method,   # Payment Method
                f"${adjusted_subtotal:.2f}",   # Subtotal (already adjusted for discount)
                f"${tax_amount:.2f}",          # Tax
                f"${total:.2f}",               # Total
                self.machine_id,               # Machine ID
                "Completed"                    # Status
            ]
            
            # Add item details (up to 15 items)
            item_count = 0
            for upc, item in self.cart_items.items():
                item_count += 1
                if item_count > 15:  # Only support up to 15 items
                    logging.warning(f"Transaction has more than 15 items, only logging first 15")
                    break
                    
                # For each item, add 6 columns: UPC, Name, Qty, Price, Total, Taxable
                row_data.extend([
                    upc,                                # Item X UPC
                    item["name"],                       # Item X Name
                    str(item["qty"]),                   # Item X Qty
                    f"${item['price']:.2f}",            # Item X Price
                    f"${item['price'] * item['qty']:.2f}", # Item X Total
                    "Yes" if item["taxable"] else "No"  # Item X Taxable
                ])
            
            # Fill remaining item slots with empty values if needed
            remaining_items = 15 - item_count
            if remaining_items > 0:
                # Each item has 6 columns
                row_data.extend([""] * (remaining_items * 6))
            
            # Append the row to the sheet
            sheet.append_row(row_data)
            logging.info(f"Successfully logged transaction {self.transaction_id} to Transactions tab")
            
            # If there was a discount, log it to the Redeemed tab
            if discount_amount > 0 and discount_info:
                self._log_discount_to_redeemed_tab(discount_info, discount_amount)
            
        except Exception as e:
            logging.error(f"Failed to log transaction details: {e}")
            import traceback
            logging.error(traceback.format_exc())

    def _log_discount_to_redeemed_tab(self, discount_info, discount_amount):
        """Log discount information to the Redeemed tab."""
        try:
            # Connect to Google Sheet
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_file(str(GS_CRED_PATH), scopes=scopes)
            gc = gspread.authorize(creds)
            
            # Open the Redeemed sheet
            sheet = gc.open(GS_SHEET_NAME).worksheet("Redeemed")
            
            # Get current date and time
            now = datetime.now()
            date_str = now.strftime("%m/%d/%Y")
            time_str = now.strftime("%H:%M:%S")
            
            # Prepare row data for Redeemed tab
            row_data = [
                f"TXN-{self.transaction_id}",                # Transaction ID
                date_str,                                     # Date
                time_str,                                     # Time
                discount_info.get('type', 'Discount'),        # Discount Type
                f"${discount_amount:.2f}",                    # Amount
                self.machine_id,                              # Machine ID
                self.current_payment_method,                  # Payment Method
                f"${sum(item['price'] * item['qty'] for item in self.cart_items.values()):.2f}",  # Subtotal (original)
                f"${sum(item['price'] * item['qty'] for item in self.cart_items.values() if item['taxable']) * (self.tax_rate / 100):.2f}",  # Tax
                f"${sum(item['price'] * item['qty'] for item in self.cart_items.values()) - discount_amount + (sum(item['price'] * item['qty'] for item in self.cart_items.values() if item['taxable']) * (self.tax_rate / 100)):.2f}"  # Total
            ]
            
            # Append the row to the sheet
            sheet.append_row(row_data)
            logging.info(f"Successfully logged discount for transaction {self.transaction_id} to Redeemed tab")
            
        except Exception as e:
            logging.error(f"Failed to log discount to Redeemed tab: {e}")
            import traceback
            logging.error(traceback.format_exc())
    


    def _thank_you_complete(self):
        """Complete the thank you process and return to idle mode."""
        logging.debug("Entering _thank_you_complete method")
        
        # Cancel timeout if it exists
        if hasattr(self, 'thank_you_timeout') and self.thank_you_timeout:
            logging.debug("Canceling thank you timeout")
            self.root.after_cancel(self.thank_you_timeout)
            self.thank_you_timeout = None
        
        # Close thank you popup if it exists
        if hasattr(self, 'thank_you_popup') and self.thank_you_popup:
            logging.debug("Destroying thank you popup")
            self.thank_you_popup.destroy()
            self.thank_you_popup = None

        # Schedule recording to end in 10 seconds
        if hasattr(self, 'security_camera') and hasattr(self, 'camera_enabled') and self.camera_enabled:
            self._schedule_recording_end()

        # Update discount usage in spreadsheet
        self._update_discount_usage()        

        # Clean up QR frame if it exists
        if hasattr(self, 'qr_frame') and self.qr_frame:
            logging.debug("Destroying QR frame")
            self.qr_frame.destroy()
            self.qr_frame = None      
        
        # Update inventory quantities in Google Sheet
        self._update_inventory_quantities()
        
        # Log transaction details to Transactions tab
        self._log_transaction_details()
        
        # Reset cart
        logging.debug("Resetting cart")
        self._reset_cart()
        
        # Hide CartMode UI elements instead of destroying them
        if hasattr(self, 'label'):
            self.label.place_forget()
        
        if hasattr(self, 'receipt_frame'):
            self.receipt_frame.place_forget()
        
        if hasattr(self, 'totals_frame'):
            self.totals_frame.place_forget()
            
        # Hide camera frame
        if hasattr(self, 'camera_frame'):
            self.camera_frame.place_forget()
        
        # Call the exit callback to return to idle mode
        if hasattr(self, 'on_exit') and callable(self.on_exit):
            logging.info("Transaction complete, calling exit callback to return to idle mode")
            self.on_exit()
        else:
            logging.warning("No exit callback found, cannot return to idle mode")

    def _update_inventory_quantities(self):
        """Update inventory quantities in Google Sheet after successful payment."""
        if not self.cart_items:
            logging.info("No items in cart to update inventory for")
            return
            
        logging.info("Updating inventory quantities in Google Sheet")
        
        try:
            # Connect to Google Sheet
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_file(str(GS_CRED_PATH), scopes=scopes)
            gc = gspread.authorize(creds)
            
            # Open the inventory sheet
            sheet = gc.open(GS_SHEET_NAME).worksheet(GS_TAB)
            
            # Get all UPCs from the sheet (column A)
            all_upcs = sheet.col_values(1)  # Column A (UPC)
            
            # Track updates for batch processing
            updates = []
            
            # Process each item in the cart
            for upc, item in self.cart_items.items():
                # Find the row for this UPC
                try:
                    # Try to find exact match first
                    row_idx = all_upcs.index(upc) + 1  # +1 because gspread is 1-indexed
                except ValueError:
                    # If not found, try variants
                    row_idx = None
                    for variant in upc_variants_from_scan(upc):
                        try:
                            row_idx = all_upcs.index(variant) + 1
                            break
                        except ValueError:
                            continue
                
                if row_idx:
                    # Get current quantity
                    current_qty_cell = f"K{row_idx}"
                    try:
                        current_qty = sheet.acell(current_qty_cell).value
                        current_qty = int(current_qty) if current_qty.strip() else 0
                    except (ValueError, AttributeError):
                        current_qty = 0
                    
                    # Calculate new quantity
                    new_qty = max(0, current_qty - item["qty"])
                    
                    # Add to batch update
                    updates.append({
                        'range': current_qty_cell,
                        'values': [[new_qty]]
                    })
                    
                    logging.info(f"Inventory update for {upc}: {current_qty} -> {new_qty} (sold {item['qty']})")
                else:
                    logging.warning(f"Could not find inventory row for UPC {upc}")
            
            # Perform batch update if we have any updates
            if updates:
                sheet.batch_update(updates)
                logging.info(f"Successfully updated {len(updates)} inventory quantities")
            
        except Exception as e:
            logging.error(f"Failed to update inventory quantities: {e}")
            import traceback
            logging.error(traceback.format_exc())
    

    def _reset_cart(self):
        """Reset the cart and related variables."""
        # Clear cart items
        self.cart_items = {}
        
        # Generate a new transaction ID
        self.transaction_id = self._generate_transaction_id()
        logging.info(f"New transaction ID generated: {self.transaction_id}")
        
        # Reset payment method
        self.current_payment_method = None
        
        # Clear discount information
        self._clear_discount_info()
        
        logging.info("Cart reset")

        
        
    def _show_text_receipt(self, payment_method, total):
        """Show a text-based receipt on screen."""
        # Calculate values needed for receipt
        subtotal = sum(item["price"] * item["qty"] for item in self.cart_items.values())
        taxable_subtotal = sum(
            item["price"] * item["qty"] 
            for item in self.cart_items.values() if item["taxable"]
        )
        tax_amount = taxable_subtotal * (self.tax_rate / 100)
        total_items = sum(item["qty"] for item in self.cart_items.values())
        
        # Format the receipt content
        receipt_text = f"{self.business_name}\n"
        receipt_text += f"{self.location}\n\n"
        receipt_text += f"Machine: {self.machine_id}\n"
        receipt_text += f"Transaction: {self.transaction_id}\n"
        receipt_text += f"Date: {datetime.now().strftime('%m/%d/%Y %H:%M:%S')}\n"
        receipt_text += "-" * 40 + "\n"
        
        # Items
        for upc, item in self.cart_items.items():
            name = item["name"]
            price = item["price"]
            qty = item["qty"]
            item_total = price * qty
            
            # Format item line - truncate long names
            if len(name) > 30:
                name = name[:27] + "..."
            
            receipt_text += f"{name}\n"
            receipt_text += f"  {qty} @ ${price:.2f} = ${item_total:.2f}\n"
        
        receipt_text += "-" * 40 + "\n"
        receipt_text += f"Items: {total_items}\n"
        receipt_text += f"Subtotal: ${subtotal:.2f}\n"
        receipt_text += f"Tax ({self.tax_rate}%): ${tax_amount:.2f}\n"
        receipt_text += f"Total: ${total:.2f}\n"
        receipt_text += f"Paid: {payment_method}\n"
        receipt_text += "-" * 40 + "\n"
        receipt_text += "Thank you for shopping with us!\n"
        
        # Show in a popup
        receipt_popup = tk.Toplevel(self.root)
        receipt_popup.title("Receipt")
        receipt_popup.geometry("400x600")
        
        # Scrollable text widget
        from tkinter import scrolledtext
        text_widget = scrolledtext.ScrolledText(receipt_popup, font=("Courier", 12))
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text_widget.insert(tk.END, receipt_text)
        text_widget.config(state=tk.DISABLED)  # Make read-only
        
        # Close button
        close_btn = tk.Button(receipt_popup, text="Close", font=("Arial", 14),
                            command=receipt_popup.destroy)
        close_btn.pack(pady=10)

    def _generate_receipt_qr_code(self, receipt_text):
        """Generate QR code for receipt that opens in SMS app."""
        try:
            import qrcode
            import urllib.parse
            
            # Format the receipt text to fit in SMS
            sms_receipt = self._format_receipt_for_sms(receipt_text)
            
            # Create the SMS URI
            sms_uri = f"sms:?body={urllib.parse.quote(sms_receipt)}"
            
            # Generate QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(sms_uri)
            qr.make(fit=True)
            
            # Create an image from the QR Code
            qr_img = qr.make_image(fill_color="black", back_color="white")
            
            # Save the QR code to a temporary file
            temp_dir = Path.home() / "SelfCheck" / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            qr_path = temp_dir / "receipt_qr.png"
            qr_img.save(qr_path)
            
            return qr_path
            
        except Exception as e:
            logging.error(f"Failed to generate receipt QR code: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return None

    def _format_receipt_for_sms(self, receipt_text):
        """Format receipt text to be suitable for SMS."""
        # Extract the important parts of the receipt
        lines = receipt_text.split('\n')
        
        # Keep header (store name)
        header = lines[0] if lines else "Receipt"
        
        # Get date/time
        date_line = next((line for line in lines if "Date:" in line), 
                        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Get items and prices
        items = []
        total_line = ""
        
        for line in lines:
            # Look for item lines (typically have a price at the end)
            if re.search(r'\$\d+\.\d{2}$', line) and "Total:" not in line:
                # Simplify item lines to save characters
                simplified = re.sub(r'\s{2,}', ' ', line.strip())
                items.append(simplified)
            
            # Capture the total line
            if "Total:" in line:
                total_line = line.strip()
        
        # Construct a compact SMS receipt
        sms_receipt = f"{header}\n{date_line}\n\n"
        
        # Add items (limit if too many)
        max_items = 10  # Adjust based on typical SMS length limits
        if len(items) > max_items:
            sms_receipt += "\n".join(items[:max_items])
            sms_receipt += f"\n...and {len(items) - max_items} more items"
        else:
            sms_receipt += "\n".join(items)
        
        # Add total
        if total_line:
            sms_receipt += f"\n\n{total_line}"
        
        # Add a footer
        sms_receipt += "\n\nThank you for shopping with us!"
        
        return sms_receipt


    
    def _format_receipt(self, total):
        """Format receipt content for display or printing."""
        # Calculate values needed for receipt
        subtotal = sum(item["price"] * item["qty"] for item in self.cart_items.values())
        
        # Apply discount if any
        discount_amount = getattr(self, 'discount_amount', 0)
        discount_type = getattr(self, 'discount_type', None)
        discount_info = getattr(self, 'current_discount', None)
        
        # Adjust subtotal after discount
        adjusted_subtotal = subtotal - discount_amount
        
        # Ensure adjusted subtotal is not negative
        adjusted_subtotal = max(0, adjusted_subtotal)
        
        # Calculate tax
        taxable_subtotal = sum(
            item["price"] * item["qty"] 
            for item in self.cart_items.values() if item["taxable"]
        )
        
        # If we have a discount, adjust taxable subtotal proportionally
        if discount_amount > 0 and subtotal > 0:
            # For total discounts, reduce taxable amount proportionally
            if discount_type in ['dollar_total', 'percent_total']:
                taxable_subtotal = max(0, taxable_subtotal * (adjusted_subtotal / subtotal))
            # For item-specific discounts, we need to check which items were discounted
            elif discount_type in ['dollar_items', 'percent_items'] and hasattr(self, 'discount_items'):
                # Calculate tax reduction for discounted taxable items
                tax_reduction = 0
                for upc, item in self.cart_items.items():
                    if item["taxable"] and any(self._match_upc(upc, discount_upc) for discount_upc in self.discount_items):
                        if discount_type == 'dollar_items':
                            # Reduce by dollar amount per item, limited by item price
                            item_discount = min(float(discount_info.get('dollars', 0)), item["price"]) * item["qty"]
                            tax_reduction += item_discount
                        else:  # percent_items
                            # Reduce by percentage of item price
                            percent = float(discount_info.get('percent', 0))
                            item_discount = item["price"] * (percent / 100) * item["qty"]
                            tax_reduction += item_discount
                
                # Adjust taxable subtotal
                taxable_subtotal = max(0, taxable_subtotal - tax_reduction)
        
        tax_amount = taxable_subtotal * (self.tax_rate / 100)
        total_items = sum(item["qty"] for item in self.cart_items.values())
        
        # Format the receipt content
        receipt_text = f"{self.business_name}\n"
        receipt_text += f"{self.location}\n\n"
        receipt_text += f"Machine: {self.machine_id}\n"
        receipt_text += f"Transaction: {self.transaction_id}\n"
        receipt_text += f"Date: {datetime.now().strftime('%m/%d/%Y %H:%M:%S')}\n"
        receipt_text += "-" * 40 + "\n"
        
        # Items
        for upc, item in self.cart_items.items():
            name = item["name"]
            price = item["price"]
            qty = item["qty"]
            item_total = price * qty
            
            # Format item line - truncate long names
            if len(name) > 30:
                name = name[:27] + "..."
            
            receipt_text += f"{name}\n"
            receipt_text += f"  {qty} @ ${price:.2f} = ${item_total:.2f}\n"
        
        receipt_text += "-" * 40 + "\n"
        receipt_text += f"Items: {total_items}\n"
        receipt_text += f"Subtotal: ${subtotal:.2f}\n"
        
        # Add discount if applicable
        if discount_amount > 0 and discount_info:
            discount_text = f"Discount ({discount_info.get('type', 'Discount')}): -${discount_amount:.2f}"
            receipt_text += f"{discount_text}\n"
            receipt_text += f"Adjusted Subtotal: ${adjusted_subtotal:.2f}\n"
        
        receipt_text += f"Tax ({self.tax_rate}%): ${tax_amount:.2f}\n"
        receipt_text += f"Total: ${total:.2f}\n"
        receipt_text += f"Paid: {getattr(self, 'current_payment_method', 'Unknown')}\n"
        receipt_text += "-" * 40 + "\n"
        receipt_text += "Thank you for shopping with us!\n"
        
        return receipt_text


    
    def _show_receipt_qr(self):
        """Show QR code for receipt that can be scanned to send via SMS."""
        # Format receipt content
        subtotal = sum(item["price"] * item["qty"] for item in self.cart_items.values())
        taxable_subtotal = sum(
            item["price"] * item["qty"] 
            for item in self.cart_items.values() if item["taxable"]
        )
        tax_amount = taxable_subtotal * (self.tax_rate / 100)
        total = subtotal + tax_amount
        
        # Format receipt
        receipt_text = self._format_receipt(total)
        
        # Generate the QR code
        qr_path = self._generate_receipt_qr_code(receipt_text)
        
        if not qr_path or not Path(qr_path).exists():
            logging.error("Failed to generate receipt QR code")
            return

        
        # Create a popup to display the QR code
        qr_frame = tk.Frame(self.root, bg="#2c3e50")
        qr_frame.place(x=0, y=0, width=WINDOW_W, height=WINDOW_H)
        
        # Add title
        title_label = tk.Label(qr_frame, text="Text Receipt", 
                              font=("Arial", 36, "bold"), bg="#2c3e50", fg="white")
        title_label.pack(pady=(50, 20))
        
        # Add instructions
        instructions = tk.Label(qr_frame, text="Scan this QR code with your phone's camera\nto send the receipt via text message",
                              font=("Arial", 24), bg="#2c3e50", fg="white", justify=tk.CENTER)
        instructions.pack(pady=(0, 30))
        
        # Display QR code
        try:
            qr_img = Image.open(qr_path)
            qr_img = qr_img.resize((400, 400), Image.LANCZOS)
            qr_photo = ImageTk.PhotoImage(qr_img)
            
            qr_label = tk.Label(qr_frame, image=qr_photo, bg="#2c3e50")
            qr_label.image = qr_photo  # Keep a reference to prevent garbage collection
            qr_label.pack(pady=20)
        except Exception as e:
            logging.error(f"Failed to display QR code: {e}")
            error_label = tk.Label(qr_frame, text="Error displaying QR code", 
                                  fg="red", bg="#2c3e50", font=("Arial", 24))
            error_label.pack(pady=20)
        
        # Store reference to the frame
        self.qr_frame = qr_frame
        
        # Set timeout to return to idle mode after 30 seconds
        self.root.after(30000, self._thank_you_complete)
    

    def print_receipt(self, payment_method, total):
        """Print a receipt using direct device access."""
        logging.info(f"Printing receipt with payment method: {payment_method}")
        try:
            # Calculate values needed for receipt
            subtotal = sum(item["price"] * item["qty"] for item in self.cart_items.values())
            
            # Apply discount if any
            discount_amount = getattr(self, 'discount_amount', 0)
            discount_type = getattr(self, 'discount_type', None)
            discount_info = getattr(self, 'current_discount', None)
            
            # Adjust subtotal after discount
            adjusted_subtotal = subtotal - discount_amount
            
            # Ensure adjusted subtotal is not negative
            adjusted_subtotal = max(0, adjusted_subtotal)
            
            # Calculate tax on adjusted subtotal
            taxable_subtotal = sum(
                item["price"] * item["qty"] 
                for item in self.cart_items.values() if item["taxable"]
            )
            
            # If we have a discount, adjust taxable subtotal proportionally
            if discount_amount > 0 and subtotal > 0:
                # For total discounts, reduce taxable amount proportionally
                if discount_type in ['dollar_total', 'percent_total']:
                    taxable_subtotal = max(0, taxable_subtotal * (adjusted_subtotal / subtotal))
                # For item-specific discounts, we need to check which items were discounted
                elif discount_type in ['dollar_items', 'percent_items'] and hasattr(self, 'discount_items'):
                    # Calculate tax reduction for discounted taxable items
                    tax_reduction = 0
                    for upc, item in self.cart_items.items():
                        if item["taxable"] and any(self._match_upc(upc, discount_upc) for discount_upc in self.discount_items):
                            if discount_type == 'dollar_items':
                                # Reduce by dollar amount per item, limited by item price
                                item_discount = min(float(discount_info.get('dollars', 0)), item["price"]) * item["qty"]
                                tax_reduction += item_discount
                            else:  # percent_items
                                # Reduce by percentage of item price
                                percent = float(discount_info.get('percent', 0))
                                item_discount = item["price"] * (percent / 100) * item["qty"]
                                tax_reduction += item_discount
                    
                    # Adjust taxable subtotal
                    taxable_subtotal = max(0, taxable_subtotal - tax_reduction)
            
            tax_amount = taxable_subtotal * (self.tax_rate / 100)
            calculated_total = adjusted_subtotal + tax_amount
            total_items = sum(item["qty"] for item in self.cart_items.values())
            
            # Format the receipt content
            receipt = []
            
            # Initialize printer
            receipt.append(b'\x1B@')
            
            # Center align for header
            receipt.append(b'\x1B\x61\x01')  # Center align
            
            # Business name - double height and width
            receipt.append(b'\x1D\x21\x11')  # Double height and width
            receipt.append(self.business_name.encode('ascii', 'replace') + b'\n')
            
            # Normal size for the rest
            receipt.append(b'\x1D\x21\x00')
            
            # Location
            receipt.append(self.location.encode('ascii', 'replace') + b'\n')
            
            # Left align for details
            receipt.append(b'\x1B\x61\x00')
            
            # Machine ID
            receipt.append(f"Machine: {self.machine_id}\n".encode('ascii', 'replace'))
            
            # Transaction ID
            receipt.append(f"Transaction: {self.transaction_id}\n".encode('ascii', 'replace'))
            
            # Date and time
            current_time = datetime.now().strftime('%m/%d/%Y %H:%M:%S')
            receipt.append(f"Date: {current_time}\n".encode('ascii', 'replace'))
            
            # Divider
            receipt.append(b'-' * 32 + b'\n')
            
            # Items
            for upc, item in self.cart_items.items():
                name = item["name"]
                price = item["price"]
                qty = item["qty"]
                item_total = price * qty
                
                # Format item line - truncate long names
                if len(name) > 30:
                    name = name[:27] + "..."
                
                receipt.append(f"{name}\n".encode('ascii', 'replace'))
                receipt.append(f"  {qty} @ ${price:.2f} = ${item_total:.2f}\n".encode('ascii', 'replace'))
            
            # Divider
            receipt.append(b'-' * 32 + b'\n')
            
            # Totals
            receipt.append(f"Items: {total_items}\n".encode('ascii', 'replace'))
            receipt.append(f"Subtotal: ${subtotal:.2f}\n".encode('ascii', 'replace'))
            
            # Add discount if applicable
            if discount_amount > 0 and discount_info:
                discount_text = f"Discount ({discount_info.get('type', 'Discount')}): -${discount_amount:.2f}"
                receipt.append(b'\x1B\x45\x01')  # Bold on
                receipt.append(discount_text.encode('ascii', 'replace') + b'\n')
                receipt.append(b'\x1B\x45\x00')  # Bold off
                receipt.append(f"Adjusted Subtotal: ${adjusted_subtotal:.2f}\n".encode('ascii', 'replace'))
            
            receipt.append(f"Tax ({self.tax_rate}%): ${tax_amount:.2f}\n".encode('ascii', 'replace'))
            
            # Bold for total - use calculated_total instead of parameter total
            receipt.append(b'\x1B\x45\x01')  # Bold on
            receipt.append(f"Total: ${calculated_total:.2f}\n".encode('ascii', 'replace'))
            receipt.append(b'\x1B\x45\x00')  # Bold off
            
            receipt.append(f"Paid: {payment_method}\n".encode('ascii', 'replace'))
            
            # Divider
            receipt.append(b'-' * 32 + b'\n')
            
            # Custom message from RMessage.txt
            try:
                rmessage_path = Path.home() / "SelfCheck" / "Cred" / "RMessage.txt"
                if rmessage_path.exists():
                    with open(rmessage_path, 'r') as f:
                        rmessage = f.read().strip()
                        receipt.append(b'\x1B\x61\x01')  # Center align
                        receipt.append(rmessage.encode('ascii', 'replace') + b'\n')
                else:
                    # Create default RMessage.txt if it doesn't exist
                    rmessage = "Thank you for shopping with us!"
                    rmessage_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(rmessage_path, 'w') as f:
                        f.write(rmessage)
                    receipt.append(b'\x1B\x61\x01')  # Center align
                    receipt.append(rmessage.encode('ascii', 'replace') + b'\n')
            except Exception as e:
                logging.error(f"Error reading/writing RMessage.txt: {e}")
                # Add a default message
                receipt.append(b'\x1B\x61\x01')  # Center align
                receipt.append(b'Thank you for shopping with us!\n')
            
            # Feed and cut
            receipt.append(b'\n\n\n\n')  # Just feed paper
            
            # Cut paper
            receipt.append(b'\x1D\x56\x00')
            
            # Combine all parts
            receipt_data = b''.join(receipt)
            
            # Save receipt to file
            receipt_path = Path.home() / "SelfCheck" / "Cred" / "last_receipt.txt"
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            with open(receipt_path, 'wb') as f:
                f.write(receipt_data)
            
            # Check if printer device exists
            if hasattr(self, 'printer_path') and self.printer_path:
                printer_path = self.printer_path
            else:
                printer_path = '/dev/usb/lp0'
                if not Path(printer_path).exists():
                    logging.error(f"Printer device not found: {printer_path}")
                    # Try alternative paths
                    alternative_paths = ['/dev/lp0', '/dev/usb/lp1', '/dev/lp1']
                    for alt_path in alternative_paths:
                        if Path(alt_path).exists():
                            logging.info(f"Found alternative printer device: {alt_path}")
                            printer_path = alt_path
                            break
                    else:
                        logging.error("No printer device found")
                        return False
            
            # Print using direct device access
            try:
                with open(printer_path, 'wb') as printer:
                    printer.write(receipt_data)
                logging.info(f"Receipt printed successfully to {printer_path}")
                return True
            except PermissionError:
                logging.error(f"Permission denied accessing printer at {printer_path}")
                messagebox.showerror("Printer Error", 
                                   f"Permission denied accessing printer.\n\n"
                                   f"Please run: sudo chmod 666 {printer_path}")
                return False
            
        except Exception as e:
            logging.error(f"Error printing receipt: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return False


    def _show_email_entry_popup(self):
        """Show popup for email entry with virtual keyboard."""
        # Cancel any existing timers
        if hasattr(self, 'timeout_after') and self.timeout_after:
            self.root.after_cancel(self.timeout_after)
            self.timeout_after = None
            
        if hasattr(self, 'email_timeout_timer') and self.email_timeout_timer:
            self.root.after_cancel(self.email_timeout_timer)
            self.email_timeout_timer = None
        
        # Create a dark overlay
        overlay = tk.Frame(self.root, bg='#000000')
        overlay.place(x=0, y=0, width=WINDOW_W, height=WINDOW_H)
        
        # Create the popup frame - use full screen for better visibility
        email_popup = tk.Frame(self.root, bg="white", bd=2, relief=tk.RAISED)
        email_popup.place(x=0, y=0, width=WINDOW_W, height=WINDOW_H)
        
        # Title at the top
        title_label = tk.Label(email_popup, text="Enter Email Address", 
                              font=("Arial", 28, "bold"), bg="white")
        title_label.pack(pady=(20, 20))
        
        # Email entry field - make it very large and prominent
        self.email_var = tk.StringVar()
        email_entry = tk.Entry(email_popup, textvariable=self.email_var, 
                              font=("Arial", 28), width=30, justify=tk.CENTER)
        email_entry.pack(pady=(0, 30), ipady=10)  # Add internal padding for taller entry
        email_entry.focus_set()
        
        # Create a frame for the keyboard
        keyboard_container = tk.Frame(email_popup, bg="white")
        keyboard_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Create rows for the keyboard - standard layout
        # Number row
        num_row = tk.Frame(keyboard_container, bg="white")
        num_row.pack(fill=tk.X, pady=5)
        
        for key in ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '-', '=']:
            btn = tk.Button(num_row, text=key, font=("Arial", 24), 
                          width=3, height=1, bg="#34495e", fg="white",
                          command=lambda k=key: self._email_key_press(k))
            btn.pack(side=tk.LEFT, padx=5, pady=5)
        
        # QWERTY row
        qwerty_row = tk.Frame(keyboard_container, bg="white")
        qwerty_row.pack(fill=tk.X, pady=5)
        
        for key in ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p', '@']:
            btn = tk.Button(qwerty_row, text=key, font=("Arial", 24), 
                          width=3, height=1, bg="#34495e", fg="white",
                          command=lambda k=key: self._email_key_press(k))
            btn.pack(side=tk.LEFT, padx=5, pady=5)
        
        # ASDF row
        asdf_row = tk.Frame(keyboard_container, bg="white")
        asdf_row.pack(fill=tk.X, pady=5)
        
        # Add some padding at the start for proper keyboard layout
        tk.Label(asdf_row, text="", width=1, bg="white").pack(side=tk.LEFT)
        
        for key in ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', '.', '_']:
            btn = tk.Button(asdf_row, text=key, font=("Arial", 24), 
                          width=3, height=1, bg="#34495e", fg="white",
                          command=lambda k=key: self._email_key_press(k))
            btn.pack(side=tk.LEFT, padx=5, pady=5)
        
        # ZXCV row
        zxcv_row = tk.Frame(keyboard_container, bg="white")
        zxcv_row.pack(fill=tk.X, pady=5)
        
        # Add more padding at the start for proper keyboard layout
        tk.Label(zxcv_row, text="", width=2, bg="white").pack(side=tk.LEFT)
        
        for key in ['z', 'x', 'c', 'v', 'b', 'n', 'm']:
            btn = tk.Button(zxcv_row, text=key, font=("Arial", 24), 
                          width=3, height=1, bg="#34495e", fg="white",
                          command=lambda k=key: self._email_key_press(k))
            btn.pack(side=tk.LEFT, padx=5, pady=5)
        
        # Special keys row
        special_row = tk.Frame(keyboard_container, bg="white")
        special_row.pack(fill=tk.X, pady=10)
        
        # Shift key
        shift_btn = tk.Button(special_row, text="Shift", font=("Arial", 24), 
                            width=6, height=1, bg="#9b59b6", fg="white",
                            command=self._email_toggle_shift)
        shift_btn.pack(side=tk.LEFT, padx=5, pady=5)
        
        # Space key
        space_btn = tk.Button(special_row, text="Space", font=("Arial", 24), 
                            width=12, height=1, bg="#7f8c8d", fg="white",
                            command=lambda: self._email_key_press(" "))
        space_btn.pack(side=tk.LEFT, padx=5, pady=5)
        
        # Backspace key
        backspace_btn = tk.Button(special_row, text="Backspace", font=("Arial", 24), 
                                width=10, height=1, bg="#e67e22", fg="white",
                                command=self._email_backspace)
        backspace_btn.pack(side=tk.LEFT, padx=5, pady=5)
        
        # Domain shortcuts row
        domain_row = tk.Frame(keyboard_container, bg="white")
        domain_row.pack(fill=tk.X, pady=10)
        
        domains = ["@gmail.com", "@yahoo.com", "@hotmail.com", ".com"]
        for domain in domains:
            domain_btn = tk.Button(domain_row, text=domain, font=("Arial", 20),
                                 bg="#3498db", fg="white", height=1,
                                 command=lambda d=domain: self._email_key_press(d))
            domain_btn.pack(side=tk.LEFT, padx=5, pady=5, fill=tk.X, expand=True)
        
        # Buttons row
        button_row = tk.Frame(keyboard_container, bg="white")
        button_row.pack(fill=tk.X, pady=(20, 10))
        
        # Cancel button
        cancel_btn = tk.Button(button_row, text="Cancel", font=("Arial", 24),
                             bg="#e74c3c", fg="white", height=2,
                             command=lambda: self._cancel_email_entry(overlay, email_popup))
        cancel_btn.pack(side=tk.LEFT, padx=10, pady=10, fill=tk.X, expand=True)
        
        # Submit button
        submit_btn = tk.Button(button_row, text="Submit", font=("Arial", 24, "bold"),
                             bg="#27ae60", fg="white", height=2,
                             command=lambda: self._send_receipt_email(self.email_var.get(), overlay, email_popup))
        submit_btn.pack(side=tk.LEFT, padx=10, pady=10, fill=tk.X, expand=True)
        
        # Store references to popup elements
        self.email_entry_popup = email_popup
        self.email_entry_overlay = overlay
        self.email_keyboard_btns = []  # Will store keyboard buttons for shift toggle
        
        # Set up a much longer timeout (3 minutes = 180 seconds)
        self.email_last_activity = time.time()
        self._start_email_entry_timeout(180)  # 3 minutes timeout
        
        # Store shift state
        self.email_shift_on = False
    
    def _email_key_press(self, key):
        """Handle key press on email keyboard."""
        current = self.email_var.get()
        self.email_var.set(current + key)
        # Reset activity timestamp
        self.email_last_activity = time.time()
    
    def _email_backspace(self):
        """Handle backspace on email keyboard."""
        current = self.email_var.get()
        self.email_var.set(current[:-1])
        # Reset activity timestamp
        self.email_last_activity = time.time()
    
    def _email_toggle_shift(self):
        """Toggle shift state for email keyboard."""
        self.email_shift_on = not self.email_shift_on
        # Reset activity timestamp
        self.email_last_activity = time.time()
        
        # TODO: Implement actual shift functionality if needed
        # This would require storing references to all letter buttons
        # and updating their text when shift is toggled
    
    def _start_email_entry_timeout(self, seconds=180):
        """Start a timeout for the email entry popup."""
        # Store the timeout timer reference
        self.email_timeout_timer = None
        
        def check_timeout():
            current_time = time.time()
            elapsed = current_time - self.email_last_activity
            
            # If timeout seconds have passed with no activity
            if elapsed >= seconds:
                logging.info(f"Email entry timeout after {seconds} seconds of inactivity")
                # Close the email entry popup
                if hasattr(self, 'email_entry_popup') and self.email_entry_popup:
                    self.email_entry_popup.destroy()
                if hasattr(self, 'email_entry_overlay') and self.email_entry_overlay:
                    self.email_entry_overlay.destroy()
                
                # Return to idle mode
                self._thank_you_complete()
                return
            
            # Check again in 1 second
            self.email_timeout_timer = self.root.after(1000, check_timeout)
        
        # Start the timeout check
        self.email_timeout_timer = self.root.after(1000, check_timeout)

        
    def _cancel_email_entry(self, overlay, popup):
        """Cancel email entry and return to thank you screen."""
        # Cancel the email timeout timer
        if hasattr(self, 'email_timeout_timer') and self.email_timeout_timer:
            self.root.after_cancel(self.email_timeout_timer)
            self.email_timeout_timer = None
            
        # Destroy popup elements
        overlay.destroy()
        popup.destroy()
        
        # Restart regular timeout timer
        self._arm_timeout()


    def _cancel_email_entry(self, overlay, popup):
        """Cancel email entry and return to thank you screen."""
        overlay.destroy()
        popup.destroy()
        
    def _send_receipt_email(self, email_address, overlay, popup):
        """Send receipt to the provided email address."""
        # Cancel the email timeout timer
        if hasattr(self, 'email_timeout_timer') and self.email_timeout_timer:
            self.root.after_cancel(self.email_timeout_timer)
            self.email_timeout_timer = None
            
        if not email_address or '@' not in email_address or '.' not in email_address:
            # Invalid email - just close and return to idle mode without showing error
            logging.warning(f"Invalid email address entered: {email_address}")
            
            # Close popup
            overlay.destroy()
            popup.destroy()
            
            # Complete the thank you process and return to idle mode
            self._thank_you_complete()
            return
            
        # Calculate the total for the subject line
        subtotal = sum(item["price"] * item["qty"] for item in self.cart_items.values())
        taxable_subtotal = sum(
            item["price"] * item["qty"] 
            for item in self.cart_items.values() if item["taxable"]
        )
        tax_amount = taxable_subtotal * (self.tax_rate / 100)
        total = subtotal + tax_amount
        
        # Format receipt content
        receipt_text = self._format_receipt_email(total)
        
        # Send email
        subject = f"Vend Las Vegas Receipt (${total:.2f})"
        
        try:
            # Attempt to send email
            self._send_email(email_address, subject, receipt_text)
            logging.info(f"Receipt email sent to {email_address}")
        except Exception as e:
            # Log error but don't show popup
            logging.error(f"Failed to send email to {email_address}: {e}")
            
            # Save receipt to file as fallback
            self._save_receipt_to_file(email_address, receipt_text)
        
        # Close popup regardless of email success/failure
        overlay.destroy()
        popup.destroy()
        
        # Always complete the thank you process and return to idle mode
        self._thank_you_complete()

    def _load_email_setting(self, filename, default_value):
        """Load an email setting from a file in the Cred directory."""
        file_path = Path.home() / "SelfCheck" / "Cred" / filename
        try:
            if file_path.exists():
                with open(file_path, 'r') as f:
                    value = f.read().strip()
                    return value if value else default_value
            else:
                # Create file with default value if it doesn't exist
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path, 'w') as f:
                    f.write(default_value)
                return default_value
        except Exception as e:
            logging.error(f"Error loading email setting from {filename}: {e}")
            return default_value

    def _send_email(self, recipient, subject, body):
        """Send email using SMTP with settings from configuration files."""
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        # Load email configuration from files
        smtp_server = self._load_email_setting("EmailServer.txt", "smtpout.secureserver.net")
        smtp_port = int(self._load_email_setting("EmailPort.txt", "587"))
        sender_email = self._load_email_setting("EmailSender.txt", "tyson@vendlasvegas.com")
        display_name = self._load_email_setting("EmailDisplayName.txt", "Vend Las Vegas No-Reply")
        reply_to = self._load_email_setting("EmailReplyTo.txt", "NoReply@vendlasvegas.com")
        
        # Load password
        password = self._load_email_setting("EmailPassword.txt", "")
        if not password:
            logging.error("Email password not set in EmailPassword.txt")
            raise ValueError("Email password not configured")
        
        # Create message
        message = MIMEMultipart()
        message["From"] = f"{display_name} <{sender_email}>"
        message["To"] = recipient
        message["Subject"] = subject
        message["Reply-To"] = reply_to
        message.attach(MIMEText(body, "plain"))
        
        try:
            # Connect to server and send
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(sender_email, password)
            server.send_message(message)
            server.quit()
            return True
        except Exception as e:
            logging.error(f"Failed to send email with primary settings: {e}")
            # Try alternative port with SSL if using standard port
            if smtp_port == 587:
                try:
                    logging.info("Trying alternative port 465 with SSL")
                    server = smtplib.SMTP_SSL(smtp_server, 465)
                    server.login(sender_email, password)
                    server.send_message(message)
                    server.quit()
                    return True
                except Exception as e2:
                    logging.error(f"Failed to send email with alternative settings: {e2}")
                    raise
            else:
                raise


    def _format_receipt_email(self, total):
        """Format receipt content for email."""
        # Calculate values needed for receipt
        subtotal = sum(item["price"] * item["qty"] for item in self.cart_items.values())
        
        # Apply discount if any
        discount_amount = getattr(self, 'discount_amount', 0)
        discount_type = getattr(self, 'discount_type', None)
        discount_info = getattr(self, 'current_discount', None)
        
        # Adjust subtotal after discount
        adjusted_subtotal = subtotal - discount_amount
        
        # Ensure adjusted subtotal is not negative
        adjusted_subtotal = max(0, adjusted_subtotal)
        
        # Calculate tax
        taxable_subtotal = sum(
            item["price"] * item["qty"] 
            for item in self.cart_items.values() if item["taxable"]
        )
        
        # If we have a discount, adjust taxable subtotal proportionally
        if discount_amount > 0 and subtotal > 0:
            # For total discounts, reduce taxable amount proportionally
            if discount_type in ['dollar_total', 'percent_total']:
                taxable_subtotal = max(0, taxable_subtotal * (adjusted_subtotal / subtotal))
            # For item-specific discounts, we need to check which items were discounted
            elif discount_type in ['dollar_items', 'percent_items'] and hasattr(self, 'discount_items'):
                # Calculate tax reduction for discounted taxable items
                tax_reduction = 0
                for upc, item in self.cart_items.items():
                    if item["taxable"] and any(self._match_upc(upc, discount_upc) for discount_upc in self.discount_items):
                        if discount_type == 'dollar_items':
                            # Reduce by dollar amount per item, limited by item price
                            item_discount = min(float(discount_info.get('dollars', 0)), item["price"]) * item["qty"]
                            tax_reduction += item_discount
                        else:  # percent_items
                            # Reduce by percentage of item price
                            percent = float(discount_info.get('percent', 0))
                            item_discount = item["price"] * (percent / 100) * item["qty"]
                            tax_reduction += item_discount
                
                # Adjust taxable subtotal
                taxable_subtotal = max(0, taxable_subtotal - tax_reduction)
        
        tax_amount = taxable_subtotal * (self.tax_rate / 100)
        total_items = sum(item["qty"] for item in self.cart_items.values())
        
        # Format the receipt content
        receipt = []
        receipt.append(f"{self.business_name}")
        receipt.append(f"{self.location}")
        receipt.append("")
        receipt.append(f"Machine: {self.machine_id}")
        receipt.append(f"Transaction: {self.transaction_id}")
        receipt.append(f"Date: {datetime.now().strftime('%m/%d/%Y %H:%M:%S')}")
        receipt.append("-" * 40)
        
        # Items
        for upc, item in self.cart_items.items():
            name = item["name"]
            price = item["price"]
            qty = item["qty"]
            item_total = price * qty
            
            receipt.append(f"{name}")
            receipt.append(f"  {qty} @ ${price:.2f} = ${item_total:.2f}")
        
        receipt.append("-" * 40)
        receipt.append(f"Items: {total_items}")
        receipt.append(f"Subtotal: ${subtotal:.2f}")
        
        # Add discount if applicable
        if discount_amount > 0 and discount_info:
            discount_text = f"Discount ({discount_info.get('type', 'Discount')}): -${discount_amount:.2f}"
            receipt.append(discount_text)
            receipt.append(f"Adjusted Subtotal: ${adjusted_subtotal:.2f}")
        
        receipt.append(f"Tax ({self.tax_rate}%): ${tax_amount:.2f}")
        receipt.append(f"Total: ${total:.2f}")
        receipt.append(f"Paid: {self.current_payment_method}")
        receipt.append("-" * 40)
        receipt.append("Thank you for shopping with us!")
        
        return "\n".join(receipt)

    def _send_email(self, recipient, subject, body):
        """Send email using SMTP with GoDaddy."""
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        # Email configuration for GoDaddy
        sender_email = "tyson@vendlasvegas.com"  # Your actual email
        display_name = "Vend Las Vegas No-Reply"  # Display name shown to recipient
        reply_to = "NoReply@vendlasvegas.com"     # Reply-to address
        smtp_server = "smtpout.secureserver.net"  # GoDaddy SMTP server
        smtp_port = 587                           # GoDaddy SMTP port with TLS
        
        # Load password from secure file
        email_creds_path = Path.home() / "SelfCheck" / "Cred" / "EmailPassword.txt"
        try:
            with open(email_creds_path, 'r') as f:
                password = f.read().strip()
        except Exception as e:
            logging.error(f"Failed to load email password: {e}")
            raise
        
        # Create message
        message = MIMEMultipart()
        message["From"] = f"{display_name} <{sender_email}>"
        message["To"] = recipient
        message["Subject"] = subject
        message["Reply-To"] = reply_to
        message.attach(MIMEText(body, "plain"))
        
        try:
            # Connect to server and send
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(sender_email, password)
            server.send_message(message)
            server.quit()
            return True
        except Exception as e:
            logging.error(f"Failed to send email: {e}")
            # Try alternative port with SSL
            try:
                logging.info("Trying alternative port with SSL")
                server = smtplib.SMTP_SSL(smtp_server, 465)
                server.login(sender_email, password)
                server.send_message(message)
                server.quit()
                return True
            except Exception as e2:
                logging.error(f"Failed to send email with alternative settings: {e2}")
                raise

    

    def _start_payment_timeout(self, timeout_seconds=45):
        """Start timeout for payment popup."""
        self.payment_last_activity = time.time()
        self.payment_timeout = None
        self.payment_timeout_seconds = timeout_seconds
        
        def check_payment_timeout():
            if not hasattr(self, 'payment_popup') or not self.payment_popup:
                return
                
            current_time = time.time()
            elapsed = current_time - self.payment_last_activity
            
            if elapsed >= self.payment_timeout_seconds:
                self._show_payment_timeout_popup()
                return
                
            self.payment_timeout = self.root.after(1000, check_payment_timeout)
            
        self.payment_timeout = self.root.after(1000, check_payment_timeout)

    def _show_payment_timeout_popup(self):
        """Show timeout popup for payment screen."""
        if hasattr(self, 'payment_timeout_popup') and self.payment_timeout_popup:
            return
            
        # Create popup
        self.payment_timeout_popup = tk.Frame(self.root, bg="white", bd=3, relief=tk.RAISED)
        self.payment_timeout_popup.place(relx=0.5, rely=0.5, width=500, height=300, anchor=tk.CENTER)
        
        # Message
        message = tk.Label(self.payment_timeout_popup, text="Do you need more time?", 
                         font=("Arial", 24, "bold"), bg="white")
        message.pack(pady=(40, 20))
        
        # Countdown
        self.payment_countdown_value = 30
        self.payment_countdown_label = tk.Label(self.payment_timeout_popup, 
                                             text=f"Returning to main menu in {self.payment_countdown_value} seconds", 
                                             font=("Arial", 18), bg="white")
        self.payment_countdown_label.pack(pady=20)
        
        # Buttons
        btn_frame = tk.Frame(self.payment_timeout_popup, bg="white")
        btn_frame.pack(pady=20, fill=tk.X)
        
        # Yes button
        yes_btn = tk.Button(btn_frame, text="Yes", font=("Arial", 18), bg="#27ae60", fg="white",
                          command=self._cancel_payment_timeout_popup)
        yes_btn.pack(side=tk.LEFT, padx=20, pady=10, fill=tk.X, expand=True)
        
        # No button
        no_btn = tk.Button(btn_frame, text="No", font=("Arial", 18), bg="#e74c3c", fg="white",
                         command=self._payment_timeout_no_response)
        no_btn.pack(side=tk.LEFT, padx=20, pady=10, fill=tk.X, expand=True)
        
        # Start countdown
        self._update_payment_countdown()

    def _update_payment_countdown(self):
        """Update the payment timeout countdown timer."""
        if not hasattr(self, 'payment_timeout_popup') or not self.payment_timeout_popup or not hasattr(self, 'payment_countdown_label'):
            return
            
        self.payment_countdown_value -= 1
        self.payment_countdown_label.config(text=f"Returning to main menu in {self.payment_countdown_value} seconds")
        
        if self.payment_countdown_value <= 0:
            self._payment_timeout_expired()
            return
            
        self.payment_countdown_after = self.root.after(1000, self._update_payment_countdown)

    def _cancel_payment_timeout_popup(self):
        """Cancel the payment timeout popup and continue."""
        if hasattr(self, 'payment_countdown_after') and self.payment_countdown_after:
            self.root.after_cancel(self.payment_countdown_after)
            self.payment_countdown_after = None
            
        if hasattr(self, 'payment_timeout_popup') and self.payment_timeout_popup:
            self.payment_timeout_popup.destroy()
            self.payment_timeout_popup = None
            
        # Reset activity timestamp
        self.payment_last_activity = time.time()
        
        # Restart timeout timer
        self._start_payment_timeout()

    def _payment_timeout_no_response(self):
        """Handle 'No' response to payment timeout popup."""
        self._close_all_payment_popups()
        self._log_cancelled_cart("Customer")
        if hasattr(self, "on_exit"):
            self.on_exit()

    def _payment_timeout_expired(self):
        """Handle payment timeout expiration."""
        self._close_all_payment_popups()
        self._log_cancelled_cart("Customer")
        if hasattr(self, "on_exit"):
            self.on_exit()

    def _show_error(self, message):
        """Show an error message."""
        # Simple messagebox for now
        from tkinter import messagebox
        messagebox.showerror("Error", message)

    def _cancel_order(self):
        """Cancel the current order."""
        if not self.cart_items:
            # Nothing to cancel
            if hasattr(self, "on_exit"):
                self.on_exit()
            return
            
        # Create a custom confirmation dialog instead of using messagebox
        self._show_cancel_confirmation()
    
    def _show_cancel_confirmation(self):
        """Show a custom confirmation dialog for order cancellation."""
        # Create a dark overlay
        overlay = tk.Frame(self.root, bg='#000000')
        overlay.place(x=0, y=0, width=WINDOW_W, height=WINDOW_H)
        
        # Create the confirmation dialog
        dialog_frame = tk.Frame(self.root, bg="white", bd=2, relief=tk.RAISED)
        dialog_width = 400
        dialog_height = 200
        x_position = (WINDOW_W - dialog_width) // 2
        y_position = (WINDOW_H - dialog_height) // 2
        dialog_frame.place(x=x_position, y=y_position, width=dialog_width, height=dialog_height)
        
        # Title
        title_label = tk.Label(dialog_frame, text="Cancel Order", 
                              font=("Arial", 18, "bold"), bg="white")
        title_label.pack(pady=(20, 10))
        
        # Message
        message_label = tk.Label(dialog_frame, 
                               text="Are you sure you want to cancel this order?", 
                               font=("Arial", 14), bg="white")
        message_label.pack(pady=10)
        
        # Buttons frame
        btn_frame = tk.Frame(dialog_frame, bg="white")
        btn_frame.pack(pady=20)
        
        # Helper function to close dialog
        def close_dialog():
            dialog_frame.destroy()
            overlay.destroy()
        
        # Yes button
        yes_btn = tk.Button(btn_frame, text="Yes", font=("Arial", 14, "bold"), 
                          bg="#e74c3c", fg="white", width=8,
                          command=lambda: self._confirm_cancel_order(close_dialog))
        yes_btn.pack(side=tk.LEFT, padx=10)
        
        # No button
        no_btn = tk.Button(btn_frame, text="No", font=("Arial", 14), 
                         bg="#3498db", fg="white", width=8,
                         command=close_dialog)
        no_btn.pack(side=tk.LEFT, padx=10)
        
        # Reset activity timestamp
        self._on_activity()
    
    def _confirm_cancel_order(self, close_callback):
        """Handle confirmation of order cancellation."""
        # Close the dialog
        close_callback()
        
        # Clear discount information
        self._clear_discount_info()
        
        # Log the cancelled cart
        self._log_cancelled_cart("Customer")
        
        # Exit to main menu
        if hasattr(self, "on_exit"):
            self.on_exit()



    def _log_cancelled_cart(self, reason):
        """Log a cancelled cart to the Service tab."""
        try:
            # Use more comprehensive scopes
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_file(str(GS_CRED_PATH), scopes=scopes)
            gc = gspread.authorize(creds)
            
            # Open the spreadsheet and worksheet
            sheet = gc.open(GS_SHEET_NAME).worksheet("Service")
            
            # Calculate cart value for logging
            subtotal = sum(item["price"] * item["qty"] for item in self.cart_items.values())
            
            # Prepare row data
            timestamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
            user = self.machine_id
            action = f"Cart Cancelled - {reason} - ${subtotal:.2f} - {len(self.cart_items)} items"
            
            # Create row with the correct format
            row = [timestamp, user, action]
            
            # Log locally first
            logging.info(f"Logging cancelled cart: {timestamp}, {user}, {action}")
            
            try:
                # Try to append to sheet
                sheet.append_row(row)
                logging.info(f"Successfully logged cancelled cart to Service tab")
            except Exception as api_error:
                logging.error(f"Error logging to Service tab: {api_error}")
                # Create a local log file as fallback
                log_dir = Path.home() / "SelfCheck" / "Logs"
                log_dir.mkdir(parents=True, exist_ok=True)
                log_file = log_dir / "transaction_log.csv"
                
                # Append to local log file
                with open(log_file, 'a') as f:
                    f.write(f"{timestamp},{user},{action}\n")
                logging.info(f"Logged cancelled cart to local file instead: {log_file}")
                
        except Exception as e:
            logging.error(f"Failed to log cancelled cart: {e}")
            import traceback
            logging.error(traceback.format_exc())

    def _log_successful_transaction(self, method, total, verification_code=None):
        """Log a successful transaction to the Service tab."""
        try:
            # Use more comprehensive scopes
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_file(str(GS_CRED_PATH), scopes=scopes)
            gc = gspread.authorize(creds)
            
            # Open the spreadsheet and worksheet
            sheet = gc.open(GS_SHEET_NAME).worksheet("Service")
            
            # Prepare row data
            timestamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
            user = self.machine_id
            
            # Include verification code in the log if provided
            if verification_code:
                action = f"Payment - {method} - ${total:.2f} - Verification: {verification_code}"
            else:
                action = f"Payment - {method} - ${total:.2f}"
            
            # Create row with the correct format
            row = [timestamp, user, action]
            
            # Log locally first
            logging.info(f"Logging successful transaction: {timestamp}, {user}, {action}")
            
            try:
                # Try to append to sheet
                sheet.append_row(row)
                logging.info(f"Successfully logged transaction to Service tab")
            except Exception as api_error:
                logging.error(f"Error logging to Service tab: {api_error}")
                # Create a local log file as fallback
                log_dir = Path.home() / "SelfCheck" / "Logs"
                log_dir.mkdir(parents=True, exist_ok=True)
                log_file = log_dir / "transaction_log.csv"
                
                # Append to local log file
                with open(log_file, 'a') as f:
                    f.write(f"{timestamp},{user},{action}\n")
                logging.info(f"Logged transaction to local file instead: {log_file}")
                
        except Exception as e:
            logging.error(f"Failed to log transaction: {e}")
            import traceback
            logging.error(traceback.format_exc())

    def _arm_timeout(self):
        """Set up inactivity timeout."""
        if self.timeout_after:
            self.root.after_cancel(self.timeout_after)

        # Reset activity timestamp to ensure full 45 seconds
        self.last_activity_ts = time.time()
            
        def check_timeout():
            current_time = time.time()
            elapsed = current_time - self.last_activity_ts
            
            if elapsed >= 45.0:  # 45 seconds
                self._show_timeout_popup()
                return
                
            self.timeout_after = self.root.after(1000, check_timeout)
            
        self.timeout_after = self.root.after(1000, check_timeout)

    def _show_timeout_popup(self):
        """Show timeout popup with countdown."""
        if self.timeout_popup:
            return
            
        # Create popup
        self.timeout_popup = tk.Frame(self.root, bg="white", bd=3, relief=tk.RAISED)
        self.timeout_popup.place(relx=0.5, rely=0.5, width=500, height=300, anchor=tk.CENTER)
        
        # Message
        message = tk.Label(self.timeout_popup, text="Do you need more time?", 
                         font=("Arial", 24, "bold"), bg="white")
        message.pack(pady=(40, 20))
        
        # Countdown
        self.countdown_value = 30
        self.countdown_label = tk.Label(self.timeout_popup, 
                                      text=f"Returning to main menu in {self.countdown_value} seconds", 
                                      font=("Arial", 18), bg="white")
        self.countdown_label.pack(pady=20)
        
        # Buttons
        btn_frame = tk.Frame(self.timeout_popup, bg="white")
        btn_frame.pack(pady=20, fill=tk.X)
        
        # Yes button
        yes_btn = tk.Button(btn_frame, text="Yes", font=("Arial", 18), bg="#27ae60", fg="white",
                          command=self._cancel_timeout_popup)
        yes_btn.pack(side=tk.LEFT, padx=20, pady=10, fill=tk.X, expand=True)
        
        # No button
        no_btn = tk.Button(btn_frame, text="No", font=("Arial", 18), bg="#e74c3c", fg="white",
                         command=self._timeout_no_response)
        no_btn.pack(side=tk.LEFT, padx=20, pady=10, fill=tk.X, expand=True)
        
        # Start countdown
        self._update_countdown()

    def _update_countdown(self):
        """Update the countdown timer."""
        if not self.timeout_popup or not self.countdown_label:
            return
            
        self.countdown_value -= 1
        self.countdown_label.config(text=f"Returning to main menu in {self.countdown_value} seconds")
        
        if self.countdown_value <= 0:
            self._timeout_expired()
            return
            
        self.countdown_after = self.root.after(1000, self._update_countdown)

    def _cancel_timeout_popup(self):
        """Cancel the timeout popup and continue shopping."""
        if self.countdown_after:
            self.root.after_cancel(self.countdown_after)
            self.countdown_after = None
            
        if self.timeout_popup:
            self.timeout_popup.destroy()
            self.timeout_popup = None
            
        # Reset activity timestamp
        self._on_activity()
        
        # Restart timeout timer
        self._arm_timeout()

    def _timeout_no_response(self):
        """Handle 'No' response to timeout popup."""
        self._log_cancelled_cart("Customer")
        if hasattr(self, "on_exit"):
            self.on_exit()

    def _timeout_expired(self):
        """Handle timeout expiration."""
        self._log_cancelled_cart("SelfCheck")
        if hasattr(self, "on_exit"):
            self.on_exit()

    def _load_upc_catalog(self):
        """Load UPC catalog from CSV file and update Tax.json from spreadsheet."""
        try:
            # Connect to Google Sheet to get latest data
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/spreadsheets",
            ]
            creds = Credentials.from_service_account_file(str(GS_CRED_PATH), scopes=scopes)
            gc = gspread.authorize(creds)
            
            # First, update the tax rate from the spreadsheet
            try:
                sheet = gc.open(GS_SHEET_NAME).worksheet(GS_CRED_TAB)
                tax_rate_str = sheet.acell('B32').value
                
                # Parse tax rate (remove % sign if present)
                if tax_rate_str:
                    tax_rate_str = tax_rate_str.replace('%', '').strip()
                    tax_rate = float(tax_rate_str)
                    
                    # Update Tax.json file
                    tax_path = CRED_DIR / "Tax.json"
                    with open(tax_path, 'w') as f:
                        json.dump({"rate": tax_rate}, f)
                    logging.info(f"Updated Tax.json with rate {tax_rate}% from spreadsheet")
                    
                    # Update the instance variable
                    self.tax_rate = tax_rate
                else:
                    logging.warning("Tax rate not found in spreadsheet cell B32")
            except Exception as e:
                logging.error(f"Failed to update tax rate from spreadsheet: {e}")
            
            # Now load the UPC catalog
            catalog_path = CRED_DIR / "upc_catalog.csv"
            if not catalog_path.exists():
                logging.error(f"UPC catalog not found: {catalog_path}")
                return
            
            # Define column mappings (same as standalone script)
            headers = [
                "UPC", "Brand", "Name", "Size", "Calories", "Sugar", "Sodium",
                "Price", "Tax %", "QTY", "Image"
            ]
            
            import csv
            with open(catalog_path, 'r', newline='') as f:
                reader = csv.DictReader(f)
                
                # Process each row
                for row in reader:
                    upc = row["UPC"].strip()
                    if not upc:
                        continue
                    
                    # Convert row dict to list for compatibility with existing code
                    row_list = [
                        upc,                   # A: UPC
                        row["Brand"],          # B: Brand
                        row["Name"],           # C: Name
                        "",                    # D: (hidden column)
                        row["Size"],           # E: Size
                        row["Calories"],       # F: Calories
                        row["Sugar"],          # G: Sugar
                        row["Sodium"],         # H: Sodium
                        row["Price"],          # I: Price
                        row["Tax %"],          # J: Tax %
                        row["QTY"],            # K: QTY
                        row["Image"]           # L: Image
                    ]
                    
                    # Store the row list for this UPC
                    self.upc_catalog[upc] = row_list
                    
                    # Also store variants
                    for variant in upc_variants_from_sheet(upc):
                        if variant != upc:
                            self.upc_catalog[variant] = row_list
                
            logging.info(f"Loaded {len(self.upc_catalog)} UPC entries from catalog")
            
        except Exception as e:
            logging.error(f"Error loading UPC catalog: {e}")

    def _load_config_files(self):
        """Load configuration from JSON files."""
        try:
            # Business name
            business_path = CRED_DIR / "BusinessName.json"
            if business_path.exists():
                try:
                    with open(business_path, 'r') as f:
                        data = json.load(f)
                        self.business_name = data.get("name", self.business_name)
                except json.JSONDecodeError:
                    logging.error(f"Invalid JSON in BusinessName.json")
                    # Create a new file with default value
                    with open(business_path, 'w') as f:
                        json.dump({"name": self.business_name}, f)
            
            # Location
            location_path = CRED_DIR / "MachineLocation.json"
            if location_path.exists():
                try:
                    with open(location_path, 'r') as f:
                        data = json.load(f)
                        self.location = data.get("location", self.location)
                except json.JSONDecodeError:
                    logging.error(f"Invalid JSON in MachineLocation.json")
                    # Create a new file with default value
                    with open(location_path, 'w') as f:
                        json.dump({"location": self.location}, f)
            
            # Machine ID
            machine_id_path = CRED_DIR / "MachineID.txt"
            if machine_id_path.exists():
                with open(machine_id_path, 'r') as f:
                    self.machine_id = f.read().strip() or self.machine_id
            
            # Tax rate
            tax_path = CRED_DIR / "Tax.json"
            if tax_path.exists():
                try:
                    with open(tax_path, 'r') as f:
                        data = json.load(f)
                        old_rate = self.tax_rate
                        self.tax_rate = float(data.get("rate", 2.9))  # Default to 2.9% if not specified
                        logging.info(f"Loaded tax rate from Tax.json: {self.tax_rate}% (was {old_rate}%)")
                except (json.JSONDecodeError, ValueError):
                    # If Tax.json is malformed, create a new one with default value
                    logging.warning(f"Tax.json is malformed, creating new file with default rate")
                    self.tax_rate = 2.9  # Default tax rate
                    with open(tax_path, 'w') as f:
                        json.dump({"rate": self.tax_rate}, f)
                    logging.info(f"Created new Tax.json with rate: {self.tax_rate}%")
            else:
                # If Tax.json doesn't exist, create it
                logging.warning(f"Tax.json not found, creating new file with default rate")
                self.tax_rate = 2.9  # Default tax rate
                with open(tax_path, 'w') as f:
                    json.dump({"rate": self.tax_rate}, f)
                logging.info(f"Created new Tax.json with rate: {self.tax_rate}%")
                
        except Exception as e:
            logging.error(f"Error loading config files: {e}")
            import traceback
            logging.error(traceback.format_exc())
            # Set default tax rate if there was an error
            self.tax_rate = 0.0

    def _load_product_image(self, image_name, target_label, size=(225, 225)):
        """
        Load a product image from cache or Google Drive.
        
        Args:
            image_name: Name of the image file
            target_label: The tk.Label widget to display the image in
            size: Tuple of (width, height) for resizing
        """
        if not image_name:
            target_label.config(image="", text="No image available")
            return
            
        # Import necessary modules
        import io
        from googleapiclient.http import MediaIoBaseDownload
        
        # Store the image reference as an attribute of the label to prevent garbage collection
        if not hasattr(target_label, 'image_ref'):
            target_label.image_ref = None
        
        try:
            # Ensure cache directory exists
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            
            # Check local cache first
            image_path = self.cache_dir / image_name
            logging.info(f"Looking for image: {image_name} at path: {image_path}")
            
            if image_path.exists():
                logging.info(f"Loading image from cache: {image_path}")
                with Image.open(image_path) as img:
                    img = img.resize(size, Image.LANCZOS)
                    photo_image = ImageTk.PhotoImage(img)
                    target_label.image_ref = photo_image  # Prevent garbage collection
                    target_label.config(image=photo_image, text="")
                    return True
            
            # If not in cache, try to download from Google Drive
            if self.drive_service:
                logging.info(f"Searching for image in Google Drive: {image_name}")
                query = f"name = '{image_name}' and trashed = false"
                results = self.drive_service.files().list(
                    q=query, spaces='drive', fields='files(id, name)').execute()
                items = results.get('files', [])
                
                if items:
                    file_id = items[0]['id']
                    logging.info(f"Found image in Drive with ID: {file_id}")
                    
                    # Download file
                    request = self.drive_service.files().get_media(fileId=file_id)
                    fh = io.BytesIO()
                    downloader = MediaIoBaseDownload(fh, request)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                    
                    # Save to cache
                    fh.seek(0)
                    with open(image_path, 'wb') as f:
                        f.write(fh.read())
                    logging.info(f"Saved image to cache: {image_path}")
                    
                    # Display image
                    with Image.open(image_path) as img:
                        img = img.resize(size, Image.LANCZOS)
                        photo_image = ImageTk.PhotoImage(img)
                        target_label.image_ref = photo_image  # Prevent garbage collection
                        target_label.config(image=photo_image, text="")
                        return True
                else:
                    logging.warning(f"Image not found in Drive: {image_name}")
                    target_label.config(image="", text="Image not found in Drive")
                    return False
            else:
                logging.warning("Drive service not available")
                target_label.config(image="", text="Drive service not available")
                return False
        except Exception as e:
            logging.error(f"Error loading image {image_name}: {e}")
            import traceback
            logging.error(traceback.format_exc())
            target_label.config(image="", text=f"Error loading image")
            return False

    def test_sheet_access(self):
        """Test access to the Google Sheet."""
        try:
            # Use more comprehensive scopes
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_file(str(GS_CRED_PATH), scopes=scopes)
            gc = gspread.authorize(creds)
            
            # Try to open the sheet
            sheet = gc.open(GS_SHEET_NAME)
            service_tab = sheet.worksheet("Service")
            
            # Try to read
            values = service_tab.get_all_values()
            logging.info(f"Successfully read {len(values)} rows from Service tab")
            
            # Try to write a test row
            test_row = [datetime.now().strftime("%m/%d/%Y %H:%M:%S"), 
                        self.machine_id, 
                        "System Started"]
            service_tab.append_row(test_row)
            logging.info("Successfully wrote test row to Service tab")
            
            return True
        except Exception as e:
            logging.error(f"Sheet access test failed: {e}")
            return False

    def check_spreadsheet_permissions(self):
        """Check and log permissions for the Google Sheet."""
        try:
            scopes = ["https://www.googleapis.com/auth/spreadsheets"]
            creds = Credentials.from_service_account_file(str(GS_CRED_PATH), scopes=scopes)
            gc = gspread.authorize(creds)
            
            # Get service account email
            service_account_info = json.loads(Path(GS_CRED_PATH).read_text())
            service_account_email = service_account_info.get('client_email', 'Unknown')
            
            logging.info(f"Service account email: {service_account_email}")
            
            # Try to open the sheet
            sheet = gc.open(GS_SHEET_NAME)
            
            # Get permissions
            permissions = sheet.list_permissions()
            
            # Log permissions
            for perm in permissions:
                role = perm.get('role', 'Unknown')
                email = perm.get('emailAddress', 'Unknown')
                perm_type = perm.get('type', 'Unknown')
                logging.info(f"Permission: {email} has {role} access (type: {perm_type})")
                
            # Check if service account has edit access
            service_account_has_access = False
            for perm in permissions:
                if perm.get('emailAddress') == service_account_email:
                    if perm.get('role') in ['writer', 'owner']:
                        service_account_has_access = True
                        break
            
            if service_account_has_access:
                logging.info("Service account has write access to the spreadsheet")
            else:
                logging.warning("Service account does NOT have write access to the spreadsheet")
                logging.warning(f"Please share the spreadsheet with {service_account_email} as an Editor")
                
            return service_account_has_access
            
        except Exception as e:
            logging.error(f"Error checking spreadsheet permissions: {e}")
            return False



# ==============================
#        SECURITY CAMERA
# ==============================

class SecurityCamera:
    """Handles camera capture for security monitoring."""
    def __init__(self):
        self.camera = None
        self.camera_running = False
        self.current_frame = None
        self.camera_thread = None
        self.recording = False
        self.video_writer = None
        self.recording_filename = None

    @staticmethod
    def is_available():
        """Check if OpenCV is available."""
        try:
            import cv2
            return True
        except ImportError:
            return False
    
        
    def initialize(self):
        """Initialize camera with V4L2 settings."""
        try:
            logging.info("Initializing security camera...")
            self.camera = cv2.VideoCapture("/dev/video0", cv2.CAP_V4L2)
            
            if not self.camera.isOpened():
                logging.error("Failed to open camera")
                self.camera = None
                return False
            
            logging.info("Camera opened successfully")
            
            # Set to the supported resolution
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 160)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 120)
            
            # Try both formats - use MJPG first as it's typically faster
            formats = [
                ("MJPG", cv2.VideoWriter_fourcc('M','J','P','G')),
                ("YUYV", cv2.VideoWriter_fourcc('Y','U','Y','V'))
            ]
            
            format_set = False
            for fmt_name, fmt_code in formats:
                logging.info(f"Trying camera format: {fmt_name}")
                self.camera.set(cv2.CAP_PROP_FOURCC, fmt_code)
                
                # Try to read a test frame
                ret, frame = self.camera.read()
                if ret:
                    logging.info(f"SUCCESS! Camera format {fmt_name} works")
                    format_set = True
                    break
            
            if not format_set:
                logging.error("Could not set a working camera format")
                self.camera.release()
                self.camera = None
                return False
                
            logging.info("Security camera initialized successfully")
            return True
            
        except Exception as e:
            logging.error(f"Error initializing camera: {e}")
            if self.camera is not None:
                self.camera.release()
            self.camera = None
            return False
    
    def start(self):
        """Start camera capture in separate thread."""
        if self.camera is None and not self.initialize():
            logging.error("Cannot start camera - initialization failed")
            return False
            
        self.camera_running = True
        self.camera_thread = threading.Thread(target=self._camera_loop, daemon=True)
        self.camera_thread.start()
        logging.info("Security camera started")
        return True
    
    def stop(self):
        """Stop camera capture."""
        self.camera_running = False
        
        # Stop recording if active
        if self.recording:
            self.stop_recording()
        
        if self.camera_thread:
            # Wait for thread to finish
            if self.camera_thread.is_alive():
                self.camera_thread.join(timeout=1.0)
            self.camera_thread = None
            
        if self.camera:
            self.camera.release()
            self.camera = None
        logging.info("Security camera stopped")
    
    def _camera_loop(self):
        """Camera capture loop running in separate thread."""
        while self.camera_running and self.camera is not None:
            try:
                ret, frame = self.camera.read()
                if ret:
                    # Convert BGR to RGB for PIL
                    self.current_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    
                    # Write frame to video if recording
                    if self.recording and self.video_writer:
                        self.video_writer.write(frame)  # Write the original BGR frame
                else:
                    logging.warning("Failed to read from camera")
                    time.sleep(0.5)  # Wait before trying again
            except Exception as e:
                logging.error(f"Camera error: {e}")
                time.sleep(1)  # Wait longer after an error
            
            time.sleep(0.1)  # ~10 FPS to reduce CPU usage
    
    def get_current_frame(self):
        """Get the current camera frame as a PIL Image."""
        if self.current_frame is None:
            return None
            
        try:
            # Convert to PIL Image
            pil_image = Image.fromarray(self.current_frame)
            return pil_image
        except Exception as e:
            logging.error(f"Error converting camera frame: {e}")
            return None
            
    def start_recording(self, filename):
        """Start recording video to a file."""
        if self.camera is None:
            logging.error("Cannot start recording - camera not initialized")
            return False
            
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            
            # Define the codec and create VideoWriter object
            fourcc = cv2.VideoWriter_fourcc(*'XVID')
            self.video_writer = cv2.VideoWriter(filename, fourcc, 10.0, (160, 120))
            
            if not self.video_writer.isOpened():
                logging.error(f"Failed to open video writer for {filename}")
                return False
                
            self.recording = True
            self.recording_filename = filename
            logging.info(f"Started recording to {filename}")
            return True
        except Exception as e:
            logging.error(f"Error starting recording: {e}")
            return False

    def stop_recording(self):
        """Stop recording video."""
        if not self.recording:
            return False
            
        try:
            self.recording = False
            if self.video_writer:
                self.video_writer.release()
                self.video_writer = None
            logging.info(f"Stopped recording to {self.recording_filename}")
            return True
        except Exception as e:
            logging.error(f"Error stopping recording: {e}")
            return False






# ==============================
#              APP
# ==============================

class App:
    def __init__(self):
        # GUI
        self.root = tk.Tk()
        self.root.attributes("-fullscreen", True)
        # Enable cursor for touch development
        self.root.config(cursor="arrow")  # Show cursor during development
        self.root.configure(bg="black")
        self.root.bind("<Escape>", lambda e: self.shutdown())
 
        # Check for OpenCV installation
        self.opencv_available = self.check_opencv_installation()

        # Initialize Google Drive service
        self.drive_service = None
        self.sheets_service = None
        self.init_google_services()

        # Load settings from Google Sheets
        self.settings = self.load_settings_from_sheet()
              
        # Attach services to root for access by all modes
        self.root.drive_service = self.drive_service
        self.root.sheets_service = self.sheets_service
        
        # Download UPC catalog and update tax rate at startup
        self.update_upc_catalog_and_tax_rate()

        # Hide the cursor
        self.hide_cursor()

        # Modes
        self.idle = IdleMode(self.root)
        self.idle.on_remote_restart = self.remote_restart
        self.price = PriceCheckMode(self.root)
        self.admin = AdminMode(self.root)
        self.mode = None
        self.cart = CartMode(self.root)

        # Buttons -> callbacks
        GPIO.setmode(GPIO.BCM)

        # Button pins
        self.PIN_RED = 5     # exit modes -> Idle
        self.PIN_GREEN = 6   # enter PriceCheck / reset for new scan / update credentials
        self.PIN_YELLOW = 12 # Available
        self.PIN_BLUE = 13   # Available
        self.PIN_CLEAR = 16  # Enter Admin mode

        # Setup with pull-up resistors
        GPIO.setup(self.PIN_RED, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.PIN_GREEN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.PIN_YELLOW, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.PIN_BLUE, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.PIN_CLEAR, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # Add event detection for all buttons
        GPIO.add_event_detect(self.PIN_RED, GPIO.FALLING, callback=self._on_red, bouncetime=300)
        GPIO.add_event_detect(self.PIN_GREEN, GPIO.FALLING, callback=self._on_green, bouncetime=300)
        GPIO.add_event_detect(self.PIN_CLEAR, GPIO.FALLING, callback=self._on_clear, bouncetime=300)

        # Hook timeout from PriceCheck
        self.price.on_timeout = lambda: self.set_mode("Idle")

        # Hook admin mode timeouts and events
        self.admin.on_exit = lambda: self.set_mode("Idle")
        self.admin.on_timeout = lambda: self.set_mode("Idle")
        self.admin.on_system_restart = self.shutdown

        # Hook touch actions with proper method names
        self.idle.on_touch_action = lambda: self.set_mode("PriceCheck")
        self.idle.on_wifi_tap = lambda: self.set_mode("Admin")
        self.idle.on_cart_action = lambda: self.set_mode("Cart")
        self.price.on_cart_action = lambda: self.set_mode("Cart")
        self.cart.on_exit = lambda: self.set_mode("Idle")


    # Button handlers
    def _on_red(self, ch):
        if self.mode == "PriceCheck" or self.mode == "Admin" or self.mode == "Cart":
            self.set_mode("Idle")

    def _on_green(self, ch):
        if self.mode == "Idle":
            self.set_mode("PriceCheck")
        elif self.mode == "PriceCheck":
            self.price._reset_for_next_scan()
        elif self.mode == "Admin":
            self.admin.update_credentials()

    def _on_clear(self, ch):
        if self.mode != "Admin":
            self.set_mode("Admin")

    def init_google_services(self):
        """Initialize Google Drive and Sheets services."""
        try:
            # Set up Google Drive API client with comprehensive scopes
            scopes = [
                'https://www.googleapis.com/auth/drive.readonly',
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive',
            ]
            
            creds = Credentials.from_service_account_file(str(GS_CRED_PATH), scopes=scopes)
            
            # Initialize Drive service
            drive_service = build('drive', 'v3', credentials=creds)
            self.drive_service = drive_service
            
            # Initialize Sheets service
            sheets_service = build('sheets', 'v4', credentials=creds)
            self.sheets_service = sheets_service
            
            # Test Drive connection by listing files
            results = drive_service.files().list(pageSize=10, fields="nextPageToken, files(id, name)").execute()
            items = results.get('files', [])
            logging.info(f"Found {len(items)} files in Google Drive folder")
            
            # Log a few file names for debugging
            if items:
                file_names = [item['name'] for item in items[:5]]
                logging.info(f"Sample files in Drive: {', '.join(file_names)}")
            
            # Test Sheets connection by getting spreadsheet info
            try:
                # Use gspread for easier sheet access
                gc = gspread.authorize(creds)
                sheet = gc.open(GS_SHEET_NAME)
                worksheets = sheet.worksheets()
                worksheet_names = [ws.title for ws in worksheets]
                logging.info(f"Found worksheets in {GS_SHEET_NAME}: {', '.join(worksheet_names)}")
                
                # Check if Service tab exists
                if "Service" in worksheet_names:
                    service_tab = sheet.worksheet("Service")
                    values = service_tab.get_all_values()
                    logging.info(f"Service tab contains {len(values)} rows")
                else:
                    logging.warning(f"Service tab not found in {GS_SHEET_NAME}")
                
                # Check permissions
                permissions = sheet.list_permissions()
                service_account_info = json.loads(Path(GS_CRED_PATH).read_text())
                service_account_email = service_account_info.get('client_email', 'Unknown')
                
                logging.info(f"Service account email: {service_account_email}")
                
                # Check if service account has edit access
                service_account_has_access = False
                for perm in permissions:
                    if perm.get('emailAddress') == service_account_email:
                        role = perm.get('role', 'Unknown')
                        logging.info(f"Service account has {role} access")
                        if role in ['writer', 'owner']:
                            service_account_has_access = True
                        break
                
                if not service_account_has_access:
                    logging.warning(f"Service account does NOT have write access to the spreadsheet")
                    logging.warning(f"Please share the spreadsheet with {service_account_email} as an Editor")
                
            except Exception as sheets_error:
                logging.error(f"Error testing Sheets access: {sheets_error}")
                
            logging.info("Google services initialized successfully")
            return True
            
        except Exception as e:
            logging.error(f"Failed to initialize Google services: {e}")
            import traceback
            logging.error(traceback.format_exc())
            self.drive_service = None
            self.sheets_service = None
            return False

    def load_settings_from_sheet(self):
        """Load settings from Google Sheets Settings tab and save to JSON file."""
        logging.info("Loading settings from Google Sheets")
        
        try:
            # Connect to Google Sheet
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/drive.readonly",
            ]
            creds = Credentials.from_service_account_file(str(GS_CRED_PATH), scopes=scopes)
            gc = gspread.authorize(creds)
            
            # Open the Settings tab
            sheet = gc.open(GS_SHEET_NAME).worksheet("Settings")
            
            # Get settings values
            venmo_status = sheet.acell('B2').value
            cashapp_status = sheet.acell('B3').value
            receipt_printer_status = sheet.acell('B4').value
            camera_status = sheet.acell('B5').value  # Add this line
            
            # Create settings dictionary
            settings = {
                "payment_options": {
                    "venmo_enabled": venmo_status == "Enable",
                    "cashapp_enabled": cashapp_status == "Enable"
                },
                "receipt_options": {
                    "print_receipt_enabled": receipt_printer_status == "Enable"
                },
                "camera_options": {
                    "security_camera_enabled": camera_status == "Enable"
                }
            }
            
            # Save to JSON file
            settings_path = Path.home() / "SelfCheck" / "Cred" / "Settings.json"
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(settings_path, 'w') as f:
                json.dump(settings, f, indent=4)
                
            logging.info(f"Settings saved to {settings_path}")
            return settings
            
        except Exception as e:
            logging.error(f"Error loading settings from sheet: {e}")
            
            # Create default settings if loading fails
            default_settings = {
                "payment_options": {
                    "venmo_enabled": True,
                    "cashapp_enabled": True
                },
                "receipt_options": {
                    "print_receipt_enabled": True
                },
                "camera_options": {
                    "security_camera_enabled": True
                }
            }
            
            # Try to save default settings
            try:
                settings_path = Path.home() / "SelfCheck" / "Cred" / "Settings.json"
                settings_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(settings_path, 'w') as f:
                    json.dump(default_settings, f, indent=4)
                    
                logging.info(f"Default settings saved to {settings_path}")
            except Exception as save_error:
                logging.error(f"Error saving default settings: {save_error}")
                
            return default_settings

        

    # Add global touch event handler for debugging
        def global_touch_handler(event):
            logging.info(f"Global touch event at ({event.x}, {event.y})")
    
        self.root.bind("<Button-1>", global_touch_handler, add="+")

    # Mode switcher
    def set_mode(self, mode_name: str):
        """Set the current mode with enhanced safety checks."""
        logging.info(f"Switching mode from {self.mode} to {mode_name}")
        
        # Validate mode_name
        if mode_name not in ["Idle", "PriceCheck", "Admin", "Cart"]:
            logging.error(f"Invalid mode requested: {mode_name}")
            mode_name = "Idle"  # Default to Idle if invalid mode requested
        
        # Stop current mode with safety checks
        try:
            if self.mode == "Idle":
                self.idle.stop()
            elif self.mode == "PriceCheck":
                self.price.stop()
            elif self.mode == "Admin":
                self.admin.stop()
            elif self.mode == "Cart":
                self.cart.stop()
        except Exception as e:
            logging.error(f"Error stopping mode {self.mode}: {e}")
            import traceback
            logging.error(traceback.format_exc())

        # Update mode
        self.mode = mode_name

        # Start new mode with safety checks
        try:
            if mode_name == "Idle":
                self.idle.start()
            elif mode_name == "PriceCheck":
                self.price.start()
            elif mode_name == "Admin":
                self.admin.start()
            elif mode_name == "Cart":
                self.cart.start()
        except Exception as e:
            logging.error(f"Error starting mode {mode_name}: {e}")
            import traceback
            logging.error(traceback.format_exc())
            # Fall back to Idle mode if starting the requested mode fails
            if mode_name != "Idle":
                logging.info("Falling back to Idle mode due to error")
                self.mode = "Idle"
                try:
                    self.idle.start()
                except Exception as e2:
                    logging.critical(f"Failed to start fallback Idle mode: {e2}")

    def run(self):
        self.set_mode("Idle")
        self.root.mainloop()
        self.shutdown()

    def hide_cursor(self):
        """Hide the mouse cursor."""
        # Create a blank/empty cursor
        blank_cursor = "none"  # This is a special name for no cursor
    
        # Apply the blank cursor to the root window
        self.root.config(cursor=blank_cursor)
    
        # Also apply to all child widgets for consistency
        for widget in self.root.winfo_children():
            widget.config(cursor=blank_cursor)

    def check_opencv_installation(self):
        """Check if OpenCV is installed and provide a warning if not."""
        try:
            import cv2
            logging.info(f"OpenCV version {cv2.__version__} is installed")
            return True
        except ImportError:
            logging.error("OpenCV (cv2) is not installed. Camera functionality will be disabled.")
            logging.error("To install OpenCV, run: sudo apt install python3-opencv")
            return False
    

    def update_upc_catalog_and_tax_rate(self):
        """Update UPC catalog and tax rate from Google Sheet."""
        try:
            # Connect to Google Sheet
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/drive.readonly",
            ]
            creds = Credentials.from_service_account_file(str(GS_CRED_PATH), scopes=scopes)
            gc = gspread.authorize(creds)
            
            # Get tax rate from Credentials tab, cell B32
            sheet = gc.open(GS_SHEET_NAME).worksheet(GS_CRED_TAB)
            tax_rate_str = sheet.acell('B32').value
            
            # Parse tax rate (remove % sign if present)
            if tax_rate_str:
                tax_rate_str = tax_rate_str.replace('%', '').strip()
                try:
                    tax_rate = float(tax_rate_str)
                    
                    # Save to Tax.json
                    tax_path = CRED_DIR / "Tax.json"
                    with open(tax_path, 'w') as f:
                        json.dump({"rate": tax_rate}, f)
                    logging.info(f"Updated Tax.json with rate: {tax_rate}% from spreadsheet")
                except ValueError:
                    logging.error(f"Invalid tax rate in spreadsheet: {tax_rate_str}")
            else:
                logging.warning("Tax rate not found in spreadsheet")
            
            # Get inventory data from Inv tab
            sheet = gc.open(GS_SHEET_NAME).worksheet(GS_TAB)
            rows = sheet.get_all_values()
            
            if not rows:
                logging.error("Sheet returned no rows")
                return
                
            # Define output headers and source column indexes (0-based) for A,B,C,E,F,G,H,I,J,K,L
            out_headers = [
                "UPC", "Brand", "Name", "Size", "Calories", "Sugar", "Sodium",
                "Price", "Tax %", "QTY", "Image"
            ]
            col_idxs = [0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11]
            
            # Map rows to records
            import csv
            records = []
            for r in rows[1:]:  # Skip header row
                if not r:  # Skip blanks
                    continue
                upc = (r[0] if len(r) > 0 else "").strip()
                if not upc:
                    continue
                vals = [(r[i].strip() if len(r) > i else "") for i in col_idxs]
                records.append(dict(zip(out_headers, vals)))
            
            # Write CSV
            CRED_DIR.mkdir(parents=True, exist_ok=True)
            catalog_path = CRED_DIR / "upc_catalog.csv"
            with open(catalog_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=out_headers)
                writer.writeheader()
                writer.writerows(records)
                
            logging.info(f"Downloaded UPC catalog with {len(records)} rows")
            
        except Exception as e:
            logging.error(f"Failed to update UPC catalog and tax rate: {e}")

    def remote_restart(self):
        """Handle remote restart command."""
        logging.info("Executing remote restart")
        self.shutdown()
        
        # Optional: Add system restart command if needed
        # import os
        # os.system("sudo reboot")

    def get_settings(self):
        """Get current settings, loading from file if necessary."""
        if not hasattr(self, 'settings') or self.settings is None:
            # Try to load from file first
            settings_path = Path.home() / "SelfCheck" / "Cred" / "Settings.json"
            if settings_path.exists():
                try:
                    with open(settings_path, 'r') as f:
                        self.settings = json.load(f)
                    logging.info("Settings loaded from file")
                except Exception as e:
                    logging.error(f"Error loading settings from file: {e}")
                    # Fall back to loading from sheet
                    self.settings = self.load_settings_from_sheet()
            else:
                # If file doesn't exist, load from sheet
                self.settings = self.load_settings_from_sheet()
        
        return self.settings
    
    

    def shutdown(self):
        try:
            if self.mode == "Idle":
                self.idle.stop()
            elif self.mode == "PriceCheck":
                self.price.stop()
            elif self.mode == "Admin":
                self.admin.stop()
            elif self.mode == "Cart":
                self.cart.stop()
        finally:
            GPIO.cleanup()
            try:
                self.root.destroy()
            except:
                pass

if __name__ == "__main__":
    App().run()
