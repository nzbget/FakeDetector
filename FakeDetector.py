#!/usr/bin/env python
#
# Fake detection script for NZBGet
#
# Copyright (C) 2014 Andrey Prygunkov <hugbug@users.sourceforge.net>
# Copyright (C) 2014 Clinton Hall <clintonhall@users.sourceforge.net>
# Copyright (C) 2014 JVM
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#

##############################################################################
### NZBGET QUEUE/POST-PROCESSING SCRIPT                                    ###

# Detect nzbs with fake media files.
#
# If a fake is detected the download is marked as bad. NZBGet removes
# the download from queue and (if option "DeleteCleanupDisk" is active) the
# downloaded files are deleted from disk. If duplicate handling is active
# (option "DupeCheck") then another duplicate is chosen for download
# if available.
# 
# The status "FAILURE/BAD" is passed to other scripts and informs them
# about failure.
#
# PP-Script version: 1.2.
#
# NOTE: This script requires Python to be installed on your system (tested
# only with Python 2.x; may not work with Python 3.x).

### NZBGET QUEUE/POST-PROCESSING SCRIPT                                    ###
##############################################################################


import os
import sys
import subprocess
import re
from xmlrpclib import ServerProxy

# Exit codes used by NZBGet for post-processing scripts.
# Queue-scripts don't have any special exit codes.
POSTPROCESS_SUCCESS=93
POSTPROCESS_NONE=95
POSTPROCESS_ERROR=94

nzbget = None
verbose = False

# Start up checks
def start_check():
	# Check if the script is called from a compatible NZBGet version (as queue-script or as pp-script)
	if not ('NZBNA_EVENT' in os.environ or 'NZBPP_DIRECTORY' in os.environ) or not 'NZBOP_ARTICLECACHE' in os.environ:
		print('*** NZBGet queue script ***')
		print('This script is supposed to be called from nzbget (14.0 or later).')
		sys.exit(1)
	
	# This script processes only certain queue events.
	# For compatibility with newer NZBGet versions it ignores event types it doesn't know
	if os.environ.get('NZBNA_EVENT') not in ['NZB_ADDED', 'FILE_DOWNLOADED', 'NZB_DOWNLOADED', None]:
		sys.exit(0)
	
	# If nzb was already marked as bad don't do any further detection
	if os.environ.get('NZBPP_STATUS') == 'FAILURE/BAD':
		sys.exit(POSTPROCESS_SUCCESS)
	
	# If called via "Post-process again" from history details dialog the download may not exist anymore
	if 'NZBPP_DIRECTORY' in os.environ and not os.path.exists(os.environ.get('NZBPP_DIRECTORY')):
		print('Destination directory doesn\'t exist, exiting')
		sys.exit(POSTPROCESS_NONE)
	
	# If nzb is already failed, don't do any further detection
	if os.environ.get('NZBPP_TOTALSTATUS') == 'FAILURE':
		sys.exit(POSTPROCESS_NONE)
	
# Check if media files present in the list of files
def contains_media(list):
	mediaExtensions = [ '.mkv', '.avi', '.divx', '.xvid', '.mov', '.wmv', '.mp4', '.mpg', '.mpeg', '.vob', '.iso', '.m4v' ]
	for item in list:
		if os.path.splitext(item)[1] in mediaExtensions:
			return True
		else:
			continue
	return False

# Check if executable files present in the list of files
# Exception: rename.bat (.sh, .exe) are ignored, sometimes valid posts include them.
def contains_executable(list):
	exExtensions = [ '.exe', '.bat', '.sh' ]
	allowNames = [ 'rename', 'Rename' ]
	for item in list:
		name, ext = os.path.splitext(item)
		if os.path.split(name)[1] != "":
			name = os.path.split(name)[1]
		if ext == '.exe' or (ext in exExtensions and not name in allowNames):
			print('[INFO] Found executable %s' % item)
			return True
		else:
			continue
	return False

# Finds untested files, comparing all files and processed files in tmp_file
def get_latest_file(dir):
	try:
		with open(tmp_file_name) as tmp_file:
			tested = tmp_file.read().splitlines()
			files = os.listdir(dir)
			return list(set(files)-set(tested))
	except:
		# tmp_file doesn't exist, all files need testing
		temp_folder = os.path.dirname(tmp_file_name)
		if not os.path.exists(temp_folder):
			os.makedirs(temp_folder)
			print('[DETAIL] Created folder ' + temp_folder)
		with open(tmp_file_name, "w") as tmp_file:
			tmp_file.write('')
			print('[DETAIL] Created temp file ' + tmp_file_name)
		return os.listdir(dir)

# Saves tested files so to not test again
def save_tested(data):
	with open(tmp_file_name, "a") as tmp_file:
		tmp_file.write(data)
		
# List contents of rar-files (without unpacking).
# That's how we detect fakes during download, when the download is not completed yet.
def list_all_rars(dir):
	files = get_latest_file(dir)
	tested = ''
	out = ''
	for file in files:
		# avoid .tmp files as corrupt
		if not "tmp" in file:
			try:
				command = [os.environ['NZBOP_UNRARCMD'], "vb", dir + '/' + file]
				if verbose:
					print('command: %s' % command)
				proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
				out_tmp, err = proc.communicate()
				out += out_tmp
				result = proc.returncode
				if verbose:
					print(out_tmp)
			except:
				print('[ERROR] Something went wrong checking %s' % file) 
		tested += file + '\n'
	save_tested(tested)
	return out.splitlines()
	
# Remove temp file in PP
def clean_up():
	try:
		if os.path.isfile(tmp_file_name):
			os.remove(tmp_file_name)
			print('[DETAIL] Removing temp file complete')
		else:
			print('[DETAIL] No temp file to remove')
	except:
		print('[ERROR] Removing temp file was unsuccesful.')

# Detect fake nzbs. Returns True if a fake is detected.
def detect_fake(name, dir):
	# Fake detection:
	# If download contains media files AND executables we consider it a fake.
	# QUEUE mode (called during download and before unpack):
	#  - if directory contains archives list their content and use the file
	#    names for detection;
	# POST-PROCESSING mode (called after unpack):
	#  - scan directroy content and use file names for detection;
	#  - TODO: check video files using ffprobe.
	#
	# It's actually not necessary to check the mode (QUEUE or POST-PROCESSING), we always do all checks.
	
	filelist = []
	dir = os.path.normpath(dir)
	filelist.extend([ o for o in os.listdir(dir) if os.path.isfile(os.path.join(dir, o)) ])
	dirlist = [ os.path.join(dir, o) for o in os.listdir(dir) if os.path.isdir(os.path.join(dir, o)) ]
	filelist.extend(list_all_rars(dir))
	for subdir in dirlist:
		filelist.extend(list_all_rars(subdir))
	fake = contains_media(filelist) and contains_executable(filelist)
	if fake:
		print('[WARNING] Download has media files and executables')
	return fake

# Establish connection to NZBGet via RPC-API
def connect_to_nzbget():
	global nzbget
	
	# First we need to know connection info: host, port and password of NZBGet server.
	# NZBGet passes all configuration options to post-processing script as
	# environment variables.
	host = os.environ['NZBOP_CONTROLIP']
	port = os.environ['NZBOP_CONTROLPORT']
	username = os.environ['NZBOP_CONTROLUSERNAME']
	password = os.environ['NZBOP_CONTROLPASSWORD']
	
	if host == '0.0.0.0': host = '127.0.0.1'
	
	# Build an URL for XML-RPC requests
	# TODO: encode username and password in URL-format
	rpcUrl = 'http://%s:%s@%s:%s/xmlrpc' % (username, password, host, port);
	
	# Create remote server object
	nzbget = ServerProxy(rpcUrl)

# Reorder inner files for earlier fake detection
def sort_inner_files():
	# Setup connection to NZBGet RPC-server
	connect_to_nzbget()

	nzb_id = int(os.environ.get('NZBNA_NZBID'))

	# Hold the list of inner files belonging to this nzb using RPC-API method "listfiles".
	# For details see http://nzbget.net/RPC_API_reference
	queued_files = nzbget.listfiles(0, 0, nzb_id)

	# Iterate through the list of files to find the last rar-file.
	# The last is the one with the highest XX in ".partXX.rar".
	regex = re.compile('.*\.part(\d+)\.rar', re.IGNORECASE)
	last_rar_file = None
	file_num = None
	file_id = None
	file_name = None
	for file in queued_files:
		match = regex.match(file['Filename'])
		if (match):
			cur_num = int(match.group(1))
			if not file_num or cur_num > file_num:
				file_num = cur_num
				file_id = file['ID']
				file_name = file['Filename']

	# Move the last rar-file to the top of file list
	if (file_id):
		print('[INFO] Moving last rar-file to the top: %s' % file_name)
		# Using RPC-method "editqueue"
		nzbget.editqueue('FileMoveTop', 0, '', [file_id])

# Script body
def main():
	# Globally define directory for storing list of tested files
	global tmp_file_name

	# Do start up check
	start_check()
	
	# That's how we determine if the download is still runnning or is completely downloaded.
	# We don't use this info in the fake detector (yet).
	Downloading = os.environ.get('NZBNA_EVENT') == 'FILE_DOWNLOADED'
	
	# Depending on the mode in which the script was called (queue-script
	# or post-processing-script) a different set of parameters (env. vars)
	# is passed. They also have different prefixes:
	#   - NZBNA_ in queue-script mode;
	#   - NZBPP_ in pp-script mode.
	Prefix = 'NZBNA_' if 'NZBNA_EVENT' in os.environ else 'NZBPP_'
	
	# Read context (what nzb is currently being processed)
	Category = os.environ[Prefix + 'CATEGORY']
	Directory = os.environ[Prefix + 'DIRECTORY']
	NzbName = os.environ[Prefix + 'NZBNAME']
	
	# Directory for storing list of tested files
	tmp_file_name = os.environ.get('NZBOP_TEMPDIR') + '/FakeDetector/' + os.environ.get(Prefix + 'NZBID')
	
	# When nzb is added to queue - reorder inner files for earlier fake detection.
	# Also it is possible that nzb was added with a category which doesn't have 
	# FakeDetector listed in the PostScript. In this case FakeDetector was not called
	# when adding nzb to queue but it is being called now and we can reorder
	# files now.
	if os.environ.get('NZBNA_EVENT') == 'NZB_ADDED' or \
			(os.environ.get('NZBNA_EVENT') == 'FILE_DOWNLOADED' and \
			os.environ.get('NZBPR_FAKEDETECTOR_SORTED') <> 'yes'):
		print('[INFO] Sorting inner files for earlier fake detection for %s' % NzbName)
		sys.stdout.flush()
		sort_inner_files()
		print('[NZB] NZBPR_FAKEDETECTOR_SORTED=yes')
		if os.environ.get('NZBNA_EVENT') == 'NZB_ADDED':
			sys.exit(POSTPROCESS_NONE)
		
	print('[DETAIL] Detecting fake for %s' % NzbName)
	sys.stdout.flush()
	
	if detect_fake(NzbName, Directory):
		# A fake is detected
		#
		# Add post-processing parameter "PPSTATUS_FAKE" for nzb-file.
		# Scripts running after fake detector can check the parameter like this:
		# if os.environ.get('NZBPR_PPSTATUS_FAKE') == 'yes':
		#     print('Marked as fake by another script')
		print('[NZB] NZBPR_PPSTATUS_FAKE=yes')
	
		# Special command telling NZBGet to mark nzb as bad. The nzb will
		# be removed from queue and become status "FAILURE/BAD".
		print('[NZB] MARK=BAD')
	else:
		# Not a fake or at least doesn't look like a fake (yet).
		#
		# When nzb is downloaded again (using "Download again" from history)
		# it may have been marked by our script as a fake. Since now the script
		# doesn't consider nzb as fake we remove the old marking. That's
		# of course a rare case that someone will redownload a fake but
		# at least during debugging of fake detector we do that all the time.
		if os.environ.get('NZBPR_PPSTATUS_FAKE') == 'yes':
			print('[NZB] NZBPR_PPSTATUS_FAKE=')

	# Remove temp file in PP
	if Prefix == 'NZBPP_':
		clean_up()
	
	print('[DETAIL] Detecting completed for %s' % NzbName)
	sys.stdout.flush()
	
# Execute main script function
main()	

# All OK, returning exit status 'POSTPROCESS_SUCCESS' (int <93>) to let NZBGet know
# that our script has successfully completed (only for pp-script mode).
sys.exit(POSTPROCESS_SUCCESS)
