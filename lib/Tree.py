
class Node(object):
  def __init__(self, token):
    self.token = token
    self.children = dict()
    
  def put(self, token): # return: created node, or preinserted node
    if not token:
      return None
    
    curNode = self.lookup(token)
    if not curNode:
      tmpNode = Node(token)
      self.children[token] = tmpNode
      return tmpNode
    else:
      return curNode
    
  def lookup(self, token): # return : node, if not: none
    if not token:
      return None
    
    try:
      curNode = self.children[token]
    except KeyError:
      return None
    else:
      return curNode

  def _print(self, depth):
    print("-" * depth + self.token)
    for key in self.children:
      self.children[key]._print(depth+1)

class Tree(Node):
  def __init__(self):
    super().__init__(token = 'ROOT')
        
  def lookupAll(self, tokenList):
    if not tokenList:
      return -1
    
    curNode = self
    for token in tokenList:
      curNode = curNode.lookup(token)
      
      if not curNode:
        return -1
    
    if not len(curNode.children):
      return 0
    else:
      return -1

  def print(self):
    print("####################### Tree Dump ##########################")
    super()._print(0)
    print("############################################################")
    