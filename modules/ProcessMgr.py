import multiprocessing
import os
import glob

from lib import procSig

MAXPROCESS = 64

class ProcessMgr(object):
  global MAXPROCESS
  
  def __init__ (self, maxProcess=MAXPROCESS):
    self.children = dict()
    self.pipes = dict()
    self.lifePipe = dict()
    self.usedFD = dict()
    self.lifeCnt = [ 0 ] * MAXPROCESS
    self.softKill = [ False ] * MAXPROCESS
    self.maxProcess = maxProcess
    
    for i in range(MAXPROCESS):
      self.pipes[i] = multiprocessing.Pipe()
      self.lifePipe[i] = multiprocessing.Pipe()

  def addProcess(self, target, args):
    if len(self.children) >= self.maxProcess:
      return None

    id = self.getUnusedNum()
    if id < 0:
      return None
    
    preFDList = getFDList()

    args = (id, self.pipes[id][1], self.lifePipe[id][1]) + args
    newProcess = multiprocessing.Process(name="Crawler[{}]".format(id), target=target, args=args, daemon=True)
    
    if not newProcess:
      return None

    self.children[id] = newProcess
    
    newProcess.start()
    
    self.initCnt(id)
    self.softKill[id] = False
    
    postFDList = getFDList()
    tmpFDList = list()
    for fd, path in postFDList.items():
      if path in list(preFDList.values()):
        continue
      
      tmpFDList.append(path)
    
    self.usedFD[id] = tmpFDList
    
    return id

  def getProcess(self, id):
    try:
      return self.children[id]
    except KeyError:
      return None
  
  def getPipe(self, id):
    try:
      return self.pipes[id][0]
    except KeyError:
      return None
  
  def isProcessAlive(self, id):
    try:
      tmp = self.children[id]
    except KeyError:
      return False
    else:
      pass
    
    return tmp.is_alive()
  
  def delProcess(self, id):
    try:
      del(self.children[id])
    except KeyError:
      pass
    
    self.initCnt(id)
    self.softKill[id] = False
  
  def checkProcess(self, id):
    pipe = self.lifePipe[id][0]
    
    try:
      while pipe.poll(0):
        data = pipe.recv()
        
        if data == "l":
          self.initCnt(id)
        elif data == "d":
          procSig.killByPID(self.getProcess(id).pid)
          return False
    except (BrokenPipeError, EOFError, OSError):
      pass
    finally:
      self.increaseCnt(id)
    
    return True
  
  def killProcess(self, id):
    import signal, time
    
    pid = self.getProcess(id).pid
    pipe = self.lifePipe[id][0]
    try:
      os.kill(pid, signal.SIGINT)
    except ProcessLookupError:
      pass
    for i in range(10):
      flag = False
      try:
        while pipe.poll(0):
          data = pipe.recv()
          if data == "d":
            flag = True
            break
      except (BrokenPipeError, EOFError, OSError):
        pass
      if flag:
        break
      time.sleep(0.1)
    procSig.killByPID(pid)
    self.initCnt(id)
  
  def initCnt(self, id):
    try:
      self.lifeCnt[id] = 0
    except KeyError:
      return False
    return True
  
  def increaseCnt(self, id):
    try:
      self.lifeCnt[id] += 1
    except KeyError:
      return False
    return True
  
  def getLifeCnt(self, id):
    try:
      return self.lifeCnt[id]
    except KeyError:
      return None
  
  def getUnusedNum(self):
    for i in range(MAXPROCESS):
      if not i in self.children.keys():
        return i
    return -1

  def setMaxProcess(self, num):
    self.maxProcess = num
  
  def getProcessNum(self):
    return len(self.children)
  
  def showProcess(self, id):
    try:
      child = self.children[id]
    except KeyError:
      return None
    
    return self.isProcessAlive(id), child.pid
  
  def showProcesses(self, flag):
    if flag == 'all':
      children = list(self.children.keys())
    elif flag == 'alive':
      children = [child for child in self.children.keys() if self.isProcessAlive(child)]
    elif flag == 'dead':
      children = [child for child in self.children.keys() if not self.isProcessAlive(child)]
    else:
      print("Wrong Format")
      return False
    
    children.sort()
    print("Children Processes", flag)
    if flag == 'all':
      for child in children:
        if self.isProcessAlive(child):
          status = 'alive'
        else:
          status = 'dead'
        print("ID: {} - {}".format(child, status))
    else:
      print(children)
    return True

def getFDList():
  fd_dir = f"/proc/{os.getpid()}/fd"
  fd_info = {}
  if os.path.exists(fd_dir):
    fds = glob.glob(f"{fd_dir}/*")
    
    for fd in fds:
      try:
        fd_num = int(os.path.basename(fd))
        path = os.readlink(fd).split(":")
        if "pipe" in path[0] or "socket" in path[0]:
          fd_info[fd_num] = (path[0], path[1][1:-1])
      except (OSError, IndexError):
        pass
    return fd_info
  else:
    return None