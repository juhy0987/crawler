
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
      return 0
    
    curNode = self.children
    for token in tokenList:
      curNode = curNode.lookup(token)
      
      if not curNode:
        return 0
      curNode = curNode.children
    
    return 1

  def print(self):
    print("####################### Tree Dump ##########################")
    super()._print(0)
    print("############################################################")
    
