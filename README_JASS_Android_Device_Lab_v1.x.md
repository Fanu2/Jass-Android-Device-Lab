# JASS Android Device Lab

**ADB-powered Android device inspection, diagnostics, live monitoring,
file management, and digital preservation laboratory.**

JASS Android Device Lab is a desktop application built with **Python +
PySide6** for working with Android devices through **Android Debug
Bridge (ADB)**.

The project is designed especially for older Android hardware and
software preservation. It combines everyday device-management functions
with structured diagnostics, live monitoring, and archival capabilities.

The current v1.x milestone has been tested against a **OnePlus 3T
(ONEPLUS A3000)** running **OxygenOS / Android 9 (SDK 28)**.

------------------------------------------------------------------------

## Project Status

**Current milestone: v1.x --- Frozen**

The v1.x series is considered a stable foundation for:

-   Android device inspection
-   ADB-based management
-   application inventory
-   file exploration
-   storage analysis
-   live diagnostics
-   device preservation
-   archive verification
-   archive browsing
-   snapshot metadata comparison

Future experimental work can be developed separately as an **Android
Legacy Lab 2.x** phase.

------------------------------------------------------------------------

## Screenshots / Core Workflow

``` text
Android Device
      │
      ▼
    ADB
      │
      ├── Device Dashboard
      ├── Applications Explorer
      ├── File Lab
      ├── Live Device Lab
      ├── Diagnostics
      │
      ▼
 Device Archive
      │
      ├── Device Report
      ├── Package Inventory
      ├── Screenshot
      ├── SHA-256 Manifest
      └── Archive Index
              │
              ▼
       Archive Manager
              │
              ├── Search
              ├── Verify
              ├── Compare
              └── Browse
```

------------------------------------------------------------------------

# Features

## 📱 Device Dashboard

The main dashboard identifies the connected Android device and presents
key information including:

-   Manufacturer
-   Model
-   Android release
-   SDK level
-   Build ID
-   Device codename
-   ADB serial
-   Battery status
-   Storage usage
-   ADB executable being used

Example tested device:

``` text
Manufacturer : OnePlus
Model        : ONEPLUS A3000
Device       : OnePlus3T
Android      : 9
SDK          : 28
Build        : ONEPLUS A3000_28_191104
Serial       : 3658313a
```

------------------------------------------------------------------------

# 📦 Applications Explorer

The Applications Explorer provides an inventory of installed Android
packages.

Capabilities include:

-   List installed packages
-   Search/filter packages
-   Distinguish user and system applications
-   Display APK paths
-   Display version information
-   Display UID
-   View package details
-   Copy APK paths
-   Export APKs where ADB permissions allow
-   Export package inventory to CSV

A tested OnePlus 3T installation contained approximately:

``` text
198 packages
```

------------------------------------------------------------------------

# 📁 Device File Lab

The File Lab provides an ADB-based file browser.

Features include:

-   Browse Android directories
-   Navigate remote paths
-   Double-click directories
-   Show file/directory type
-   Show file size
-   Show permissions
-   Show modified time
-   Pull files from the device
-   Push files to the device
-   Execute ADB shell commands

The application handles Android 9 shared-storage mapping and uses:

``` text
/storage/emulated/0
```

for the normal user-accessible internal storage area.

Convenient shortcuts include:

-   Internal Storage
-   Pictures
-   DCIM
-   Download

------------------------------------------------------------------------

# 💽 Storage Analyzer

The storage tools provide:

-   Human-readable file sizes
-   File type detection
-   Sorting
-   Folder analysis
-   Recursive folder-size analysis
-   Largest-directory inspection
-   Pull Folder
-   Archive Folder

This makes the File Lab useful not only for browsing but also for
examining how storage is being used on older Android devices.

------------------------------------------------------------------------

# 📦 Device Archive

The archive system creates a structured preservation snapshot of a
connected device.

An archive resembles:

``` text
JASS_Android_Device_Archive_<serial>_<timestamp>/
│
├── device_report.txt
├── ARCHIVE_INDEX.json
├── SHA256SUMS.txt
│
├── reports/
│   ├── device_properties.txt
│   ├── battery_report.txt
│   ├── storage_report.txt
│   ├── memory_report.txt
│   ├── packages_raw.txt
│   ├── packages.csv
│   └── adb_version.txt
│
└── screenshots/
    └── device_screen.png
```

The archive records important device metadata and captures a screenshot
at the time of archival.

------------------------------------------------------------------------

# 🔐 SHA-256 Integrity

Each archive can contain a SHA-256 manifest:

``` text
SHA256SUMS.txt
```

The manifest can later be verified through **Archive Manager**.

This provides a simple integrity check for preserved device snapshots.

The verification process:

``` text
Archive
   │
   ├── Read SHA256SUMS.txt
   ├── Recalculate file hashes
   ├── Compare expected hashes
   └── PASS / FAIL
```

------------------------------------------------------------------------

# 📊 Live Device Lab

The Live Device Lab provides continuously refreshed device telemetry.

Current monitoring includes:

### CPU

-   Current CPU utilization
-   Logical CPU count

### RAM

-   Used memory
-   Total memory
-   Percentage used

### Battery

-   Battery percentage
-   Temperature
-   Voltage
-   Charging state

### Storage

-   `/data` total space
-   Used space
-   Free space
-   Percentage used

### Network

-   IPv4 address/interface information
-   Network information available through Android's normal ADB shell

### Uptime

-   Device uptime

### Processes

A live process table displays:

-   PID
-   CPU usage
-   Process name

The dashboard supports automatic refresh at approximately three-second
intervals.

A **Performance Snapshot** can also be saved as a text report.

------------------------------------------------------------------------

# 🩺 Device Diagnostics

The Diagnostics module performs structured, **non-destructive** checks.

Checks include:

-   ADB connection
-   Device identity
-   Android version
-   SDK
-   Build
-   CPU / ABI
-   Battery telemetry
-   Storage
-   RAM
-   Network interface
-   Uptime
-   SELinux state
-   ADB privilege level
-   USB state
-   Display power state
-   Package inventory

Diagnostics can be exported as a text report.

The tool does **not** attempt privilege escalation or root access.

------------------------------------------------------------------------

# 📚 Archive Manager

Archive Manager provides a central workspace for previously created
device archives.

Features include:

-   Recursive archive discovery
-   Archive search
-   Device metadata display
-   Package count
-   Screenshot availability
-   Device report viewing
-   SHA-256 verification
-   Archive-folder opening
-   Archived screenshot opening
-   Metadata comparison

The manager maintains a lightweight SQLite metadata database:

``` text
JASS_Android_Archive_Manager.sqlite3
```

The database is used to index archive metadata and does not replace the
actual archives.

------------------------------------------------------------------------

# 📊 Snapshot Comparison

Archive Manager supports selecting two archives and comparing their
recorded metadata.

The comparison can examine:

-   Serial
-   Manufacturer
-   Model
-   Android version
-   SDK
-   Build
-   Package count
-   Screenshot availability

This provides a foundation for tracking an Android device over time.

The comparison is based on recorded archive metadata. It does not claim
that every file or package is identical unless those contents are
separately compared.

------------------------------------------------------------------------

# 🖥️ Device Tools

The main application provides direct access to:

  Tool             Purpose
  ---------------- ---------------------------------------
  📦 Apps          Installed application inventory
  📁 Files         Android file browser
  📦 Archive       Create device preservation archive
  📚 Archives      Browse and verify archived snapshots
  🩺 Diagnostics   Non-destructive device checks
  📊 Live Lab      Live telemetry and process monitoring
  📸 Screenshot    Capture device screen
  ↻ Reboot         Reboot through ADB
  ⌘ ADB Shell      Interactive ADB shell
  ▤ Logcat         Recent device logs

------------------------------------------------------------------------

# 🔌 ADB Requirements

JASS Android Device Lab requires **ADB / Android Platform Tools**.

On Windows, the application can locate ADB from common locations
including:

``` text
PATH
ANDROID_HOME\platform-tools
ANDROID_SDK_ROOT\platform-tools
Standard Android SDK locations
C:\Android\platform-tools
Downloads\platform-tools
Downloads\platform-tools-latest-windows\platform-tools
```

The application also provides an **Browse ADB...** option when automatic
discovery does not find the executable.

------------------------------------------------------------------------

# 📱 Preparing an Android Device

For normal USB ADB operation:

1.  Enable **Developer Options**.
2.  Enable **USB debugging**.
3.  Connect the Android device by USB.
4.  Accept the RSA debugging authorization prompt on the phone.
5.  Start JASS Android Device Lab.
6.  Confirm that the device appears as:

``` text
device
```

with ADB.

Verify from PowerShell if required:

``` powershell
adb devices
```

Example:

``` text
List of devices attached
3658313a    device
```

------------------------------------------------------------------------

# ▶️ Running the Application

The application is a Python/PySide6 desktop application.

Example:

``` powershell
py .\JASS_Android_Device_Lab_v1.7.1.py
```

Use the current v1.x source available in the project/repository.

------------------------------------------------------------------------

# 🧪 Tested Device

The primary validation device for the current milestone is:

``` text
Device       : OnePlus 3T
Model        : ONEPLUS A3000
Android      : 9
SDK          : 28
Build        : ONEPLUS A3000_28_191104
ADB Serial   : 3658313a
RAM          : approximately 5.6 GB reported by Android
Storage      : approximately 113 GB /data
```

The project was developed iteratively against this real device,
including:

-   ADB connection
-   package inventory
-   file browsing
-   storage inspection
-   screenshot capture
-   archive creation
-   SHA-256 verification
-   live monitoring
-   process inspection
-   diagnostics
-   archive indexing

------------------------------------------------------------------------

# 🔒 Security and Scope

JASS Android Device Lab operates through the permissions exposed by
normal ADB access.

It does **not**:

-   bypass Android security
-   exploit the device
-   automatically root the device
-   attempt privilege escalation
-   circumvent application sandboxing
-   defeat lock-screen security
-   modify protected system partitions without appropriate permissions

Some information or operations may therefore be unavailable on
non-rooted devices.

The application is intended for legitimate device administration,
diagnostics, preservation, research, and personal lab use.

------------------------------------------------------------------------

# 🗃️ Preservation Philosophy

The project is more than an Android utility.

It is intended as a small **digital preservation laboratory** for aging
Android hardware.

A device can be preserved as a series of dated snapshots:

``` text
Device
  │
  ├── Snapshot 01
  ├── Snapshot 02
  ├── Snapshot 03
  └── ...
```

Each snapshot can preserve:

-   identity
-   build information
-   installed-package inventory
-   battery state
-   storage state
-   memory information
-   ADB version
-   screenshot
-   integrity hashes

This creates a historical record of a device without requiring
unrestricted system access.

------------------------------------------------------------------------

# 🧭 Development Roadmap

## v1.x --- Frozen Foundation

Completed:

-   [x] ADB discovery
-   [x] Device dashboard
-   [x] Applications Explorer
-   [x] File Lab
-   [x] Storage Analyzer
-   [x] Device Archive
-   [x] SHA-256 manifests
-   [x] Device screenshots
-   [x] Live Device Lab
-   [x] CPU/RAM monitoring
-   [x] Battery monitoring
-   [x] Network monitoring
-   [x] Process monitoring
-   [x] Device Diagnostics
-   [x] Archive Manager
-   [x] Archive verification
-   [x] Snapshot metadata comparison

------------------------------------------------------------------------

# 🔭 Future --- Android Legacy Lab 2.x

Future development can be treated as a separate major phase rather than
expanding the v1.x foundation indefinitely.

Possible areas include:

-   Legacy Android application preservation
-   APK analysis
-   Package-to-package comparison
-   Historical Android build research
-   ROM/build documentation
-   Extended device inventory
-   Wireless ADB workflows
-   Device migration tools
-   Application-data preservation where permitted
-   Offline Android software cataloguing
-   Legacy-device research workspaces
-   More advanced snapshot comparison
-   Timeline-based device history

These features are intentionally outside the frozen v1.x foundation.

------------------------------------------------------------------------

# 🧰 Technology

-   **Python**
-   **PySide6**
-   **ADB / Android Platform Tools**
-   **SQLite**
-   **JSON**
-   **CSV**
-   **SHA-256**
-   Windows / Linux compatible development approach

No heavy machine-learning framework is required.

------------------------------------------------------------------------

# 📁 Project Philosophy

JASS Android Device Lab follows the broader JASS approach:

> **Build practical tools that preserve, inspect, understand and extend
> the useful life of technology.**

The project combines:

**Device Management**

-   

**Diagnostics**

-   

**Digital Preservation**

-   

**Legacy Technology Research**

------------------------------------------------------------------------

# 📌 Current Milestone

**JASS Android Device Lab v1.x --- Frozen**

The current release provides a complete foundation for connecting to,
inspecting, monitoring, diagnosing, and preserving an Android device
through ADB.

Tested successfully with:

**OnePlus 3T / ONEPLUS A3000 / Android 9 / SDK 28**

------------------------------------------------------------------------

## JASS Digital Lab

Part of the **JASS Digital Lab** collection --- a practical software
laboratory for preserving, exploring, and building useful tools around
technology, data, language, legacy systems, and personal digital
knowledge.
