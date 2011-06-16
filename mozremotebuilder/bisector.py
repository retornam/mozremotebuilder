#!/usr/bin/env python
# ***** BEGIN LICENSE BLOCK *****
# Version: MPL 1.1/GPL 2.0/LGPL 2.1
#
# The contents of this file are subject to the Mozilla Public License Version
# 1.1 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License
# for the specific language governing rights and limitations under the
# License.
#
# The Original Code is Mozilla Corporation Code.
#
# The Initial Developer of the Original Code is
# Samuel C Liu
#
# Contributor(s): Sam Liu <sam@ambushnetworks.com>
#
# Alternatively, the contents of this file may be used under the terms of
# either the GNU General Public License Version 2 or later (the "GPL"), or
# the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
# in which case the provisions of the GPL or the LGPL are applicable instead
# of those above. If you wish to allow use of your version of this file only
# under the terms of either the GPL or the LGPL, and not to allow others to
# use your version of this file under the terms of the MPL, indicate your
# decision by deleting the provisions above and replace them with the notice
# and other provisions required by the GPL or the LGPL. If you do not delete
# the provisions above, a recipient may use your version of this file under
# the terms of any one of the MPL, the GPL or the LGPL.
#
# ***** END LICENSE BLOCK *****

from caller import BuildCaller
from utils import strsplit, download_url, get_date, get_platform
from xml.dom import minidom
from collections import deque
from optparse import OptionParser

from mozrunner import FirefoxProfile
from mozrunner import ThunderbirdProfile
from mozrunner import Runner

#For monitoring if build is done via Pulse
from threading import Thread, Condition
from pulsebuildmonitor import PulseBuildMonitor

from multiprocessing import Queue

import simplejson as json
import os, socket, urllib, math, datetime, sys, shutil

from mozrunner import Runner, FirefoxRunner
from mozInstall import MozInstaller
from mozInstall import rmdirRecursive

# Condition Variable for knowing if a new try build has completed
cv = Condition()

# Keep a queue of pulse messages as they come in.
# We pop them off and check if they're relevant to us.
lastCompleted = Queue()


class BuildMonitor(PulseBuildMonitor, Thread):
    '''
    This class signals via condition variable that our build is done
    Uses Pulse (http://pulse.mozilla.org)
    '''
    def __init__(self, logger=None, port=8034, **kwargs):
        self.logger = logger
        self.port = port
        self.builds = {}
        PulseBuildMonitor.__init__(self, logger=self.logger, **kwargs)
        Thread.__init__(self)

    def onBuildComplete(self, builddata):
        #Called when a pulse message comes in

        #print "=============================="
        #print "DEBUG: "+ str(builddata['buildurl'])
        #print json.dumps(builddata)
        #print "=============================="

        lastCompleted.put(str(builddata['buildurl']))
        cv.acquire()
        cv.notifyAll() #let thread know that a build came in!
        cv.release()


class FFRunner():
    # Calls FirefoxRunner with the right parameters
    def __init__(self, name="firefox", installDir=os.path.join(os.path.expanduser("~"),"remotebisectorapp")):
        self.name = name
        platform=get_platform()
        if platform['name'] == "Windows":
            if platform['bits'] == '64':
                print "No builds available for 64 bit Windows"
                sys.exit()
            self.buildRegex = ".*win32.zip"
            self.processName = self.name + ".exe"
            self.binary = os.path.join(installDir, self.name, self.name + ".exe")
        elif platform['name'] == "Linux":
            self.processName = self.name + "-bin"
            self.binary = os.path.join(installDir, self.name, self.name)
            if platform['bits'] == '64':
                self.buildRegex = ".*linux-x86_64.tar.bz2"
            else:
                self.buildRegex = ".*linux-i686.tar.bz2"
        elif platform['name'] == "Mac":
            self.buildRegex = ".*mac.*\.dmg"
            self.processName = self.name + "-bin"
            self.binary = os.path.join(installDir, "Mozilla.app/Contents/MacOS", self.name + "-bin")

    def run(self):
        self.runner = FirefoxRunner(binary=self.binary)
        self.runner.start()


class CommitBisector():
    def __init__(self, good, bad, byChangeset=0, host="localhost", port=9999):
        #if byChangeset = 0, good is the startdate, bad is the enddate
        #if byChangeset = 1, good is the good changeset, bad is the bad changeset
        self.left = 0
        self.right = 0
        self.good = good
        self.bad = bad
        self.log = []
        self.byChangeset = byChangeset
        self.fetchPushlog(good, bad, byChangeset)
        self.done = 0
        self.host = host
        self.port = port

    def getChangesets(self):
        #Wrapper function: fetch pushlog if it doesn't exist, otherwise return existing log.
        if(len(self.log)==0):
            return self.fetchPushlog(self.good, self.bad, self.byChangeset)
        else:
            return self.log

    def fetchPushlog(self, good, bad, c):
        #Fetch pushlog and parse out the changeset hashes
        if int(c) == 1:
            pushlog_url = 'http://hg.mozilla.org/mozilla-central/pushlog?fromchange=' + good + '&tochange=' + bad
            print "Fetching changesets from "+pushlog_url+"\n"
        else:
            pushlog_url = 'http://hg.mozilla.org/mozilla-central/pushlog?startdate=' + good + '&enddate=' + bad
            print "Fetching changesets from "+pushlog_url+"\n"

        #Parsing XML. TODO: CHANGE TO JSON
        dom = minidom.parse(urllib.urlopen(pushlog_url))

        changesets = [] #deque([])
        for node in dom.getElementsByTagNameNS('http://www.w3.org/2005/Atom','title'):
            changeset = node.childNodes[0].data
            hash = changeset.split(" ")[1]
            changesets.append(hash)

        if int(c) == 1:
            changesets.append("filler") #HACK has to do with moz-central pushlog not returning
                                        #the actual range requested: they're one short, which
                                        #threw off my algo. off-by-one errors ftl

        if(len(changesets) > 0):
            changesets.pop(0)        #HACK parsing -- eliminate extra "pushlog" text tag.
        else:
            print "\nError: invalid date or commit range"
            sys.exit()

        if(len(changesets)==0):
            print "\nError: invalid date or commit range"
            sys.exit()

        self.right = len(changesets)-1
        self.log = changesets

        return changesets

    def getMiddle(self):
        difference = math.ceil((self.right-self.left) / 2)
        return int(self.left+difference)

    def nextChangeset(self):
        return self.log[self.getMiddle()]

    def bisectLog(self, verdict="good"):
        # Change left/right until they're the same (binary search)
        # Return false when answer is found!
        if int(math.fabs(self.left - self.right)) == 0:
            print "\nFirst bad commit: "+self.log[self.left] #found the answer!
            self.done = 1
            return self.log[self.left]

        if verdict=="forward" or verdict=="g" or verdict=="good":
            self.right = self.getMiddle()
        else: #assume anything else means backward bisect
            self.left = self.getMiddle()

        if int(math.fabs(self.left - self.right)) == 1:
            print "\nFirst bad commit: "+self.log[self.left] #found the answer!
            self.done = 1
            return self.log[self.left]

        self.done = 0
        return None

    def download(self, url=None, dest=None):
        if url:
            if not dest:
                dest = os.path.basename(url)
            print "\nDownloading build...\n"
            download_url(url, dest) #see utils module
            self.dest = dest
            return True
        else:
            return False


    def go(self):
        #First, set up the listener for Pulse in another thread
        monitor = BuildMonitor(tree=['try'], label='woo@mozilla.com|latest_build_monitor_' + socket.gethostname())
        monitor.start()
        monitor_thread = Thread(target=monitor.listen)
        monitor_thread.setDaemon(True)
        monitor_thread.start()

        #Call the commit bisector!
        while(self.done == 0):
            print "Testing changeset " + self.nextChangeset()

            if self.nextChangeset() == self.bad:
                # Handle edge case, if user's input has difference 0
                self.bisectLog(verdict="bad")
            else:
                caller = BuildCaller(host=self.host,port=self.port,data=self.nextChangeset())
                response = caller.getChangeset() #should return changeset of try commit

                print "Waiting for " + response + " to show up in the build log..."

                cv.acquire()
                downloadURL = lastCompleted.get()
                while downloadURL.count(response) < 1:
                    print "Waiting for " + response + " to show up in the build log..."
                    cv.wait()
                    downloadURL = lastCompleted.get()
                cv.release()

                print downloadURL + " is the URL we need to download from! yep."

                #Make download directory
                downloadDirectory = os.path.join(os.path.expanduser("~"), "remotebisectorapp")
                if not os.path.exists(downloadDirectory):
                    os.mkdir(downloadDirectory)
                else:
                    #Make clean each time because we don't know if a file was already downloaded
                    shutil.rmtree(downloadDirectory)
                    os.mkdir(downloadDirectory)

                #Download it
                downloadedFile = os.path.join(downloadDirectory,os.path.basename(downloadURL))
                self.download(url=downloadURL,dest=downloadedFile)

                #Call MozInstall on it
                try:
                    MozInstaller(src=downloadedFile, dest=downloadDirectory, dest_app="Mozilla.app")
                except:
                    print "Install failed. Marking as bad."
                    self.bisectLog(verdict="bad")
                    #This is the most graceful way I can think of dealing with build fail
                    continue


                #Run the installed build.
                try:
                    runner = FFRunner(installDir=downloadDirectory)
                    runner.run()
                except:
                    print "Failed to start firefox. You can manually start it from the remotebisectorapp directory."
                    #Graceful failure of the runner -- ask the user to run it themselves.
                    #Turns out to be kind of good in a bunch of ways.
                    pass

                verdict = ""
                while verdict != 'good' and verdict != 'bad' and verdict != 'b' and verdict != 'g':
                    verdict = raw_input("Was this changeset good or bad? (type 'good' or 'bad' and press Enter): ")
                self.bisectLog(verdict=verdict)


def cli():
    parser = OptionParser()
    parser.add_option("-b", "--bad", dest="bad",help="first known bad date (or changeset, use -c flag)",
                      metavar="YYYY-MM-DD", default=str(datetime.date.today()))
    parser.add_option("-g", "--good", dest="good",help="last known good date (or changeset, use -c flag)",
                      metavar="YYYY-MM-DD", default=None)
    parser.add_option("-c", "--changesets", dest="byChangeset",help="set to 1 if you are using changesets instead of dates, default 0 (dates)",metavar="[0 or 1]", default=0)
    parser.add_option("-s", "--server", dest="hostname",help="hostname of mozbuildserver",
                      metavar="somedomain.com", default="localhost")
    parser.add_option("-p", "--port", dest="port",help="server port",
                      metavar="9999", default=9999)
    (options, args) = parser.parse_args()

    if not options.good and options.byChangeset == 0:
        options.good = str(datetime.date.today())
        print "No 'good' date specified, using " + options.good


    bisector = CommitBisector(options.good, options.bad, byChangeset=options.byChangeset, host=options.hostname, port=options.port)
    bisector.go()


if __name__ == "__main__":
    cli()
