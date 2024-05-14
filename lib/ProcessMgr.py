import multiprocessing

class ProcessMgr(object):
  def __init__ (self, maxProcess=0):
    self.children = dict()
    self.pipes = dict()
    self.lifeCnt = [ 0 ] * 128
    self.psNum = [ False ] * 128
    self.maxProcess = maxProcess

  def addProcess(self, target, args):
    if len(self.children) == self.maxProcess:
      return None

    id = self.getUnusedNum()
    if id < 0:
      return None
    
    parentConn, childConn = multiprocessing.Pipe()
    args = (id, childConn) + args
    newProcess = multiprocessing.Process(name="Crawler[{}]".format(id), target=target, args=args, daemon=True)
    
    if not newProcess:
      return None

    self.children[id] = newProcess
    self.pipes[id] = parentConn
    newProcess.start()
    self.initCnt(id)
    return id

  def getProcess(self, id):
    try:
      return self.children[id]
    except KeyError:
      return None
  
  def getPipe(self, id):
    try:
      return self.pipes[id]
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
      del(self.pipes[id])
    except KeyError:
      pass
    else:
      self.psNum[id] = False
  
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
      
  def setUnusedNum(self, id):
    self.psNum[id] = False
  
  def getUnusedNum(self):
    if False in self.psNum:
      tmp = self.psNum.index(False)
      self.psNum[tmp] = True
      return tmp
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
    
    return self.isProcessAlive(id)
  
  def showProcesses(self, flag):
    if flag == 'all':
      children = self.children.keys()
    elif flag == 'alive':
      children = [child for child in self.children.keys() if self.isProcessAlive(child)]
    elif flag == 'dead':
      children = [child for child in self.children.keys() if not self.isProcessAlive(child)]
    else:
      print("Wrong Format")
      return False
    
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
    