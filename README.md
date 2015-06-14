# FakeDetector
Fake detection script for [NZBGet](http://nzbget.net).

Authors:
- Andrey Prygunkov <hugbug@users.sourceforge.net>
- Clinton Hall <clintonhall@users.sourceforge.net>
- JVM <jvmed@users.sourceforge.net>

Detects nzbs with fake media files. If a fake is detected the download is marked as bad. NZBGet removes the download from queue and (if option "DeleteCleanupDisk" is active) the downloaded files are deleted from disk. If duplicate handling is active (option "DupeCheck") then another duplicate is chosen for download if available.

The status "FAILURE/BAD" is passed to other scripts and informs them about failure.

For more info and support please visit forum topic [PP-Script FakeDetector](http://nzbget.net/forum/viewtopic.php?f=8&t=1394).

NOTE: This script requires Python to be installed on your system (tested only with Python 2.x; may not work with Python 3.x).
