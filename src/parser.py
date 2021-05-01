# Yacc example

import ply.yacc as yacc
import sys
import pydot
import copy
import json

# Get the token map from the lexer.  This is required.
from lexer import tokens, keywords
precedence = (
     ('nonassoc', 'IFX'),
     ('nonassoc', 'ELSE')
 )

# in scope name, 0 denotes global, 1 denotes loop and 2 denotes if/switch, 3 denotes function
cur_num = 0
curType = []
curFuncReturnType = ''
symbol_table = []
symbol_table.append({})
global_symbol_table = {}
currentScope = 0
nextScope = 1
parent = {}
parent[0] = 0
offset = {}
offset[0] = 0
loopingDepth = 0
switchDepth = 0
size={}
size['int'] = 4
size['char'] = 1
size['float'] = 4
continueStack = []
breakStack = []
scope_to_function = {}
scope_to_function[0] = 'global'
nextstat = 0 # next instruction pointer
emit_array = [] #address code array, each element is a quad, which has [operator, source1, source2, destination]
label_cnt = 0
var_cnt = 0
CONST_SCOPE = -10
pre_append_in_symbol_table_list = ['printf', 'scanf','malloc']
local_vars = {}
func_arguments = {}
local_vars['global'] = []
strings = {}
functionScope = {}
def pre_append_in_symbol_table():
  for symbol in pre_append_in_symbol_table_list:
    symbol_table[0][symbol] = {}
    symbol_table[0][symbol]['isFunc'] = 1
    symbol_table[0][symbol]['argumentList'] = ['char *','int']
    symbol_table[0][symbol]['type'] = 'int'
    func_arguments[symbol] = ['char *','int']
    local_vars[symbol] = []

class Node:
  def __init__(self,name = '',val = '',lno = 0,type = '',children = '',scope = 0, array = [], maxDepth = 0,isFunc = 0,
    parentStruct = '', level = 0,ast = None, place = None, trueList = [], falseList = [], continueList = [], breakList = [], nextList = [],
    quad = None, expr = [], label = [], tind = '', addr = ''):
    self.name = name
    self.val = val
    self.type = type
    self.lno = lno
    self.scope = scope
    self.array = array
    self.maxDepth = maxDepth
    self.isFunc = isFunc
    self.parentStruct = parentStruct
    self.ast = ast
    self.level = level
    self.place = place
    self.trueList = trueList
    self.falseList = falseList
    self.continueList = continueList
    self.breakList = breakList
    self.nextList = nextList
    self.quad = quad
    self.expr = expr
    self.label = label
    self.tind = tind
    self.addr = addr
    if children:
      self.children = children
    else:
      self.children = []

    # add more later
ts_unit = Node('START',val = '',type ='' ,children = [])

############ Address Code generation functions ############

def emit(op, s1, s2, dest):
  global emit_array
  global nextstat
  emit_array.append([str(op), str(s1), str(s2), str(dest)])
  nextstat += 1

def backpatch(to_patch, instr):
  # we are expecting to_patch to be a list of integers here
  # when the operator is goto, the quad will be: [goto, instr number, , ]
  global emit_array
  for i in range(len(to_patch)):
    emit_array[to_patch[i]][1] = str(instr)

def merge(list1, list2):
  return (list1 + list2)

def make_list(i = -1):
  new_list = []
  if i == -1:
    return new_list
  else:
    new_list.append(int(i))
  return new_list

def _new_var():
  global var_cnt
  s = "__t_" + str(var_cnt)
  var_cnt += 1
  return s

def insert_in_sym_table(tmp_name, dtype, value=0):
  symbol_table[currentScope][tmp_name] = {}
  symbol_table[currentScope][tmp_name]['type'] = dtype
  symbol_table[currentScope][tmp_name]['size'] = get_data_type_size(dtype)
  symbol_table[currentScope][tmp_name]['value'] = value

def get_new_tmp(dtype, value=0):
  tmp_name = _new_var()
  insert_in_sym_table(tmp_name, dtype, value)
  return tmp_name

def get_label():
  global label_cnt
  s = "__l" + str(label_cnt)
  label_cnt += 1
  return s


# def handle_pointer(arr):
#   return 'int'

def int_or_real(dtype):
  arr = dtype.split()
  if ('*' in arr):
    return 'int'
  if 'long' in arr:
    return 'int' 
  elif ( ('int' in arr) or ('char' in arr) or ('short' in arr) ):
    return 'int'
  else:
    return 'real'

def handle_binary_emit(p0, p1, p2, p3):
  operator = extract_if_tuple(p2)
  higher_data_type = int_or_real(get_higher_data_type(p1.type , p3.type))
  return_tmp = get_new_tmp(higher_data_type)
  p0.place = return_tmp
  if (int_or_real(p1.type) != higher_data_type):
    tmp = get_new_tmp(higher_data_type)
    change_data_type_emit(p1.type, higher_data_type, p1.place, tmp)
    emit(higher_data_type + '_' + operator, tmp, p3.place, p0.place)
  elif (int_or_real(p3.type) != higher_data_type):
    tmp = get_new_tmp(higher_data_type)
    change_data_type_emit(p3.type, higher_data_type, p3.place, tmp)
    emit(higher_data_type + '_' + operator, p1.place, tmp, p0.place)
  else:
    emit(int_or_real(p1.type) + '_' + operator, p1.place, p3.place, p0.place)
  return p0, p1, p2, p3

def change_data_type_emit(source_dtype, dest_dtype, source_place, dest_place):
  emit(int_or_real(source_dtype) + '_' + int_or_real(dest_dtype) + '_' + '=', source_place, '', dest_place)
  #Note: here dest would be the LHS of the expression, but to maintain sanity it is inserted in right

def extract_if_tuple(p2):
  if (type(p2) is tuple):
    return str(p2[0])
  else:
    return str(p2)

def get_higher_data_type(type_1 , type_2):
  if (type_1 == '' or type_2 == ''):
    return ''
  if(type_1.endswith('*')):
    return type_1
  if(type_2.endswith('*')):
    return type_2
  to_num = {}
  to_num['char'] = 0
  to_num['short'] = 1
  to_num['int'] = 2
  to_num['long'] = 3
  to_num['float'] = 4
  to_num['double'] = 5
  to_str = {}
  to_str[0] = 'char'
  to_str[1] = 'short'
  to_str[2] = 'int'
  to_str[3] = 'long'
  to_str[4] = 'float'
  to_str[5] = 'double'
  type_1 =  type_1.split()[-1]
  type_2 =  type_2.split()[-1]
  if (type_1 not in to_num) or type_2 not in to_num:
    return str(-1)
  num_type_1 = to_num[type_1]
  num_type_2 = to_num[type_2]
  return to_str[max(num_type_1 , num_type_2)]

def get_data_type_size(type_1):
  if (type_1 == ''):
    return 0
  type_size = {}
  type_size['char'] = 1
  type_size['short'] = 2
  type_size['int'] = 4
  type_size['long'] = 8
  type_size['float'] = 4
  type_size['double'] = 8
  type_size['void'] = 0
  if(type_1.endswith('*')):
    return 8
  if( type_1.startswith('struct') or type_1.startswith('union')):
    curscp = currentScope
    while(parent[curscp] != curscp):
      if(type_1 in symbol_table[curscp].keys()):
        break
      curscp = parent[curscp]
    if (curscp == 0):
      if(type_1 not in symbol_table[curscp].keys()):
        return -1 # If id is not found in symbol table
    return symbol_table[curscp][type_1]['size']    
  type_1 = type_1.split()[-1]
  if type_1 not in type_size.keys():
    return -1
  return type_size[type_1]

def ignore_1(s):
  if(s == "}"):
    return True
  elif(s == "{"):
    return True
  elif(s == ")"):
    return True
  elif(s == "("):
    return True
  elif(s == ";"):
    return True
  elif(s == '['):
    return True
  elif(s == ']'):
    return True
  elif(s == ','):
    return True
  return False

def find_if_ID_is_declared(id,lineno):
  curscp = currentScope
  while(parent[curscp] != curscp):
    if(id in symbol_table[curscp].keys()):
      return curscp
    curscp = parent[curscp]
  if (curscp == 0):
    if(id in symbol_table[curscp].keys()):
      return curscp
  print (lineno, 'COMPILATION ERROR: unary_expression ' + id + ' not declared')
  return -1

def find_scope(id, lineno = -1): #default value kept, because it is not needed, and has been passed in code at some places
  curscp = currentScope
  while(parent[curscp] != curscp):
    if(id in symbol_table[curscp].keys()):
      return curscp
    curscp = parent[curscp]
  if (curscp == 0):
    if(id in symbol_table[curscp].keys()):
      return curscp
  return -1


def check_invalid_operation_on_function(node):
  found_scope = find_scope(node.val, node.lno)
  if (found_scope != -1) and (node.isFunc >= 1):
    print("Compilation Error at line", str(node.lno), ":Invalid operation on", node.val)


def build_AST(p,nope = []):
  global cur_num
  calling_func_name = sys._getframe(1).f_code.co_name
  calling_rule_name = calling_func_name[2:]
  length = len(p)
  if(length == 2):
    if(type(p[1]) is Node):
      return p[1].ast
    else:
      return p[1]
  else:
    cur_num += 1
    p_count = cur_num
    i = 1
    open('graph1.dot','a').write("\n" + str(p_count) + "[label=\"" + calling_rule_name.replace('"',"") + "\"]") ## make new vertex in dot file
    for child in range(1,length,1):
      if(i in nope):
        i += 1
        continue
      i += 1
      if(type(p[child]) is Node and p[child].ast is None):
        continue
      global child_num 
      global child_val
      if(type(p[child]) is not Node):
        if(type(p[child]) is tuple):
          if(ignore_1(p[child][0]) is False):
            open('graph1.dot','a').write("\n" + str(p_count) + " -> " + str(p[child][1]))
        else:
          if(ignore_1(p[child]) is False):
            cur_num += 1
            open('graph1.dot','a').write("\n" + str(cur_num) + "[label=\"" + str(p[child]).replace('"',"") + "\"]")
            p[child] = (p[child],cur_num)
            open('graph1.dot','a').write("\n" + str(p_count) + " -> " + str(p[child][1]))
      else:
        if(type(p[child].ast) is tuple):
          if(ignore_1(p[child].ast[0]) is False):
            open('graph1.dot','a').write("\n" + str(p_count) + " -> " + str(p[child].ast[1]))
        else:
          if(ignore_1(p[child].ast) is False):
            cur_num += 1
            open('graph1.dot','a').write("\n" + str(cur_num) + "[label=\"" + str(p[child].ast).replace('"',"") + "\"]")
            p[child].ast = (p[child].ast,cur_num)
            open('graph1.dot','a').write("\n" + str(p_count) + " -> " + str(p[child].ast[1]))

    return (calling_rule_name,p_count)


def p_primary_expression_0(p):
  '''primary_expression : ID'''
  p[0] = Node(name = 'PrimaryExpression',val = p[1],lno = p.lineno(1),type = '',children = [], place = p[1])
  temp = find_if_ID_is_declared(p[1],p.lineno(1))
  if(temp != -1):
    p[0].place = p[0].place + '_' + str(temp)
    # if('type' in symbol_table[temp][p[1]]):
    p[0].type = symbol_table[temp][p[1]]['type']
    if('array' in symbol_table[temp][p[1]].keys()):
      p[0].level = len(symbol_table[temp][p[1]]['array'])
    if('isFunc' in symbol_table[temp][p[1]]):
      p[0].isFunc = 1
    p[0].ast = build_AST(p)


def p_primary_expression_1(p):
  '''primary_expression : OCTAL_CONST
                | HEX_CONST
                | BIN_CONST
                | LPAREN expression RPAREN
  '''
  # p[0] = build_AST(p)
  if(len(p) == 4):
    p[0] = p[2]
    # p[0].name = 'primaryExpression'
    # place copied automatically
  else:
    p[0] = Node(name = 'PrimaryExpression',val = p[1],lno = p.lineno(1),type = 'int',children = [], place = p[1])
  p[0].ast = build_AST(p)
    

def p_primary_expression_2(p):
  '''primary_expression : CHAR_CONST'''
  p[0] = Node(name = 'ConstantExpression',val = p[1],lno = p.lineno(1),type = 'char',children = [], place = p[1])
  p[0].ast = build_AST(p)

def p_primary_expression_3(p):
  '''primary_expression : INT_CONST'''
  p[0] = Node(name = 'ConstantExpression',val = p[1],lno = p.lineno(1),type = 'int',children = [], place = p[1])
  p[0].ast = build_AST(p)

def p_primary_expression_4(p):
  '''primary_expression : FLOAT_CONST'''
  p[0] = Node(name = 'ConstantExpression',val = p[1],lno = p.lineno(1),type = 'float',children = [], place = p[1])
  p[0].ast = build_AST(p)

def p_primary_expression_5(p):
  '''primary_expression : STRING_LITERAL'''
  p[0] = Node(name = 'ConstantExpression',val = p[1],lno = p.lineno(1),type = 'char *',children = [], place = get_new_tmp('char'))
  strings[p[0].place] = p[1]
  p[0].ast = build_AST(p)

########################

def p_postfix_expression_1(p):
  '''postfix_expression : primary_expression'''
  p[0] = p[1]
  p[0].ast = build_AST(p)

def p_postfix_expression_2(p):
  '''postfix_expression : postfix_expression LSQUAREBRACKET expression RSQUAREBRACKET'''
  # check if value should be p[1].val
  p[0] = Node(name = 'ArrayExpression',val = p[1].val,lno = p[1].lno,type = p[1].type,children = [p[1],p[3]],isFunc=p[1].isFunc, parentStruct = p[1].parentStruct, place = p[1].place)
  p[0].array = copy.deepcopy(p[1].array)
  p[0].array.append(p[3].val)
  p[0].level = p[1].level - 1
  tempScope = find_scope(p[1].val, p.lineno(1))
  p[0].ast = build_AST(p)
  if(p[0].level == -1):
    print("COMPILATION ERROR at line ", str(p[1].lno), ", incorrect number of dimensions specified for " + p[1].val)

  temp_ind = get_new_tmp('int')

  if(tempScope != -1):
    d = len(symbol_table[tempScope][p[0].val]['array']) - 1 - p[0].level
    if d == 0:
      emit('int_=', p[3].place, '', temp_ind)
    else:
      v1 = get_new_tmp('int')
      emit('int_*', p[1].tind, symbol_table[tempScope][p[0].val]['array'][d-1], v1)
      emit('int_+', v1, p[3].place, temp_ind)

  if(p[0].level == 0 and len(p[0].array) > 0):
    v1 = get_new_tmp('int')
    emit('int_*', temp_ind, get_data_type_size(p[1].type), v1)
    v2 = get_new_tmp('int')
    if(len(p[1].addr) > 0):
      emit('int_=', p[1].addr, '', v2)
    else:
      emit('addr', p[0].place, '', v2)
    v3 = get_new_tmp('int')
    emit('int_+', v2, v1, v3)
    v4 = get_new_tmp(p[1].type)
    emit('*', v3, '', v4)
    p[0].place = v4
    p[0].addr = v3
  elif(len(p[0].array) > 0):
    p[0].tind = temp_ind


  curscp = currentScope
  if(p[3].type not in ['char', 'short', 'int', 'long']):
    print("Compilation Error: Array index at line ", p[3].lno, " is not of compatible type")

def p_postfix_expression_3(p):
  '''postfix_expression : postfix_expression LPAREN RPAREN'''
  p[0] = Node(name = 'FunctionCall1',val = p[1].val,lno = p[1].lno,type = p[1].type,children = [p[1]],isFunc=0, place = p[1].place)
  p[0].ast = build_AST(p)
  if(p[1].val not in symbol_table[0].keys() or 'isFunc' not in symbol_table[0][p[1].val].keys()):
    print('COMPILATION ERROR at line ' + str(p[1].lno) + ': no function with name ' + p[1].val + ' declared')
  elif(len(symbol_table[0][p[1].val]['argumentList']) != 0):
    print("Syntax Error at line",p[1].lno,"Incorrect number of arguments for function call") 
  retVal = ''
  if(p[1].type != 'void'):
    retVal = get_new_tmp(p[1].type)
  emit('call', 0, retVal, p[1].val)
  p[0].place = retVal


def p_postfix_expression_4(p):
  '''postfix_expression : postfix_expression LPAREN argument_expression_list RPAREN'''
  p[0] = Node(name = 'FunctionCall2',val = p[1].val,lno = p[1].lno,type = p[1].type,children = [],isFunc=0, place = p[1].place)
  # print(p[1].val)
  p[0].ast = build_AST(p)
  if(p[1].val not in symbol_table[0].keys() or 'isFunc' not in symbol_table[0][p[1].val].keys()):
    print('COMPILATION ERROR at line :' + str(p[1].lno) + ': no function with name ' + p[1].val + ' declared')
  elif(len(symbol_table[0][p[1].val]['argumentList']) != len(p[3].children) and p[1].val not in pre_append_in_symbol_table_list):
    print("Syntax Error at line " + str(p[1].lno) + " Incorrect number of arguments for function call")
  else:
    i = 0
    for arguments in symbol_table[0][p[1].val]['argumentList']:
      curVal = p[3].children[i].val
      if(curVal not in symbol_table[currentScope].keys()):
        continue
      curType = symbol_table[currentScope][curVal]['type']
      if(curType.split()[-1] != arguments.split()[-1]):
        print("warning at line " + str(p[1].lno), ": Type mismatch in argument " + str(i+1) + " of function call, " + 'actual type : ' + arguments + ', called with : ' + curType)
      i += 1
    for param in reversed(p[3].children):
      emit('param', '', '', param.place)
  retVal = ''
  if(p[1].type != 'void'):
    retVal = get_new_tmp(p[1].type)
  emit('call', len(p[3].children), retVal, p[1].val)
  p[0].place = retVal
  #check if function argument_list_expression matches with the actual one
  


def p_postfix_expression_5(p):
  '''postfix_expression : postfix_expression PERIOD ID
  | postfix_expression ARROW ID'''
  # no period in ast, but ID should always be present, making a tempNode to show 
  # ID as child of p[0].
  # TODO : This is the reduction of p1.x, where x is in ID, and postfix_expression stores p1
  # TODO : p[1].val should be defined in symbol table
  # TODO : p[3] should be a field of (get from symbol table - struct point)

  if (not p[1].name.startswith('Period')):
    struct_scope = find_scope(p[1].val , p[1].lno)
    if struct_scope == -1 or p[1].val not in symbol_table[struct_scope].keys():
      print("COMPILATION ERROR at line " + str(p[1].lno) + " : " + p[1].val + " not declared")

  p[0] = Node(name = 'PeriodOrArrowExpression',val = p[3],lno = p[1].lno,type = p[1].type,children = [])
  p[0].ast = build_AST(p)
  struct_name = p[1].type
  if (struct_name.endswith('*') and p[2][0] == '.') or (not struct_name.endswith('*') and p[2][0] == '->') :
    print("COMPILATION ERROR at line " + str(p[1].lno) + " : invalid operator " +  " on " + struct_name)
    return
  if(not struct_name.startswith('struct')):
    print("COMPILATION ERROR at line " + str(p[1].lno) + ", " + p[1].val + " is not a struct")
    return

  found_scope = find_scope(struct_name , p[1].lno) 
  flag = 0 
  for curr_list in symbol_table[found_scope][struct_name]['field_list']:

    if curr_list[1] == p[3][0]:
      flag = 1 
      p[0].type = curr_list[0]
      p[0].parentStruct = struct_name
      if(len(curr_list) == 5):
        p[0].level = len(curr_list[4])
  if(p[0].level == -1):
    print("COMPILATION ERROR at line ", str(p[1].lno), ", incorrect number of dimensions specified for " + p[1].val)
    return
  if flag == 0 :
    print("COMPILATION ERROR at line " + str(p[1].lno) + " : field " + " not declared in " + struct_name)
    return
  # structure things , do later

  # 3AC Code Handling
  for curr_list in symbol_table[found_scope][struct_name]['field_list']:
    if curr_list[1] == p[3][0]:
      tmp = get_new_tmp('int')
      if(len(p[1].addr) > 0):
        emit('int_=',p[1].addr, '', tmp)  
      else:
        emit('addr',p[1].place, '', tmp)
      tmp2 = get_new_tmp(curr_list[0])
      emit('int_+',tmp, curr_list[3], tmp2)
      tmp3 = get_new_tmp(curr_list[0])
      emit('*',tmp2,'',tmp3)
      p[0].place = tmp3
      p[0].addr = tmp2
      break
      




def p_postfix_expression_6(p):
  '''postfix_expression : postfix_expression INCREMENT
	| postfix_expression DECREMENT'''
  tmp = get_new_tmp(p[1].type)
  p[0] = Node(name = 'IncrementOrDecrementExpression',val = p[1].val,lno = p[1].lno,type = p[1].type,children = [], place = tmp)
  p[0].ast = build_AST(p)
  found_scope = find_scope(p[1].val, p[1].lno)
  if (found_scope != -1) and ((p[1].isFunc >= 1) or ('struct' in p[1].type.split())):
    print("Compilation Error at line", str(p[1].lno), ":Invalid operation on", p[1].val)
  # emit(p[1].val + p[2])
  emit(int_or_real(p[1].type) + '_=', p[1].place, '', tmp)
  # emit(int_or_real(p[1].type) + '_' + p[2][0][:-1], '1' ,p[1].place, p[1].place)
  if (extract_if_tuple(p[2]) == '++'):
    emit('inc', '', '', p[1].place)
  if (extract_if_tuple(p[2]) == '--'):
    emit('dec', '', '', p[1].place)

#################

def p_argument_expression_list(p):
  '''argument_expression_list : assignment_expression
                              | argument_expression_list COMMA assignment_expression
  '''
  if(len(p) == 2):
    #left val empty here for now
    p[0] = Node(name = 'ArgumentExpressionList',val = '',lno = p[1].lno,type = p[1].type,children = [p[1]])
    p[0].ast = build_AST(p)
  else:
    #check if name will always be equal to ArgumentExpressionList
    # heavy doubt
    p[0] = p[1]
    p[0].children.append(p[3])
    p[0].ast = build_AST(p,[2])
  # TODO: Handle emit
##################


def p_unary_expression_1(p):
  '''unary_expression : postfix_expression
                      | INCREMENT unary_expression
                      | DECREMENT unary_expression
  '''
  if(len(p) == 2):
    p[0] = p[1]
    p[0].ast = build_AST(p)
  else:
    #check lineno
    #also check if child should be added or not
    tempNode = Node(name = '',val = p[1],lno = p[2].lno,type = '',children = '')
    p[0] = Node(name = 'UnaryOperation',val = p[2].val,lno = p[2].lno,type = p[2].type,children = [tempNode,p[2]], place = p[2].place)
    p[0].ast = build_AST(p)
    #Can't think of a case where this is invalid
    found_scope = find_scope(p[2].val, p[2].lno)
    if (found_scope != -1) and ((p[2].isFunc >= 1) or ('struct' in p[2].type.split())):
      print("Compilation Error at line", str(p[2].lno), ":Invalid operation on", p[2].val)
    
    if (extract_if_tuple(p[1]) == '++'):
      emit('inc', '', '', p[2].place)
    if (extract_if_tuple(p[1]) == '--'):
      emit('dec', '', '', p[2].place)


def p_unary_expression_2(p):
  '''unary_expression : unary_operator cast_expression'''
  # p[1] can be &,*,+,-,~,!
  # TODO: Handle pointers
  if(p[1].val == '&'):
    # no '&' child added, will deal in traversal
    p[0] = Node(name = 'AddressOfVariable',val = p[2].val,lno = p[2].lno,type = p[2].type + ' *',children = [p[2]])
    p[0].ast = build_AST(p)
    tmp = get_new_tmp(p[2].type + ' *')
    if(p[2].addr is not None):
      emit('int_=', p[2].addr, '', tmp)
    else:
      emit('addr',p[2].place,'',tmp)
    p[0].place = tmp
  elif(p[1].val == '*'):
    if(not p[2].type.endswith('*')):
      print('COMPILATION ERROR at line ' + str(p[1].lno) + ' cannot dereference variable of type ' + p[2].type)
    p[0] = Node(name = 'PointerVariable',val = p[2].val,lno = p[2].lno,type = p[2].type[:-2],children = [p[2]])
    p[0].ast = build_AST(p)
    tmp = get_new_tmp(p[2].type[:-2])
    emit('*',p[2].place,'',tmp)
    p[0].place = tmp
    p[0].addr = p[2].place
  elif(p[1].val == '-'):
    tmp = get_new_tmp(p[2].type)
    p[0] = Node(name = 'UnaryOperationMinus',val = p[2].val,lno = p[2].lno,type = p[2].type,children = [p[2]], place = tmp)
    p[0].ast = build_AST(p)
    emit(int_or_real(p[2].type) + '_' + 'uminus', p[2].place, '', p[0].place)
  elif(p[1].val == '~'):
    tmp = get_new_tmp(p[2].type)
    p[0] = Node(name = 'UnaryOperationMinus',val = p[2].val,lno = p[2].lno,type = p[2].type,children = [p[2]], place = tmp)
    p[0].ast = build_AST(p)
    emit(int_or_real(p[2].type) + '_' + 'bitwisenot', p[2].place, '', p[0].place)
  elif(p[1].val == '!'):
    tmp = get_new_tmp(p[2].type)
    p[0] = Node(name = 'UnaryOperationMinus',val = p[2].val,lno = p[2].lno,type = p[2].type,children = [p[2]], place = tmp)
    p[0].ast = build_AST(p)
    l1 = get_label()
    l2 = get_label()
    emit('ifgoto', p[2].place, 'eq 0', l1)
    emit('int_=', '0', '', p[0].place)
    emit('goto', '', '', l2)
    emit('label', '', '', l1)
    emit('int_=', '1', '', p[0].place)
    emit('label', '', '', l2)
  else:
    p[0] = Node(name = 'UnaryOperation',val = p[2].val,lno = p[2].lno,type = p[2].type,children = [], place = p[2].place)
    p[0].ast = build_AST(p)
  # TODO: check if function can have these
  # TODO: Handle '~' and '!' in 3ac

def p_unary_expression_3(p):
  '''unary_expression : SIZEOF unary_expression'''
  # should I add SIZEOF in children
  p[0] = Node(name = 'SizeOf',val = p[2].val,lno = p[2].lno,type = p[2].type,children = [p[2]])
  p[0].ast = build_AST(p)
  # TODO: Handle 3ac

def p_unary_expression_4(p):
  '''unary_expression : SIZEOF LPAREN type_name RPAREN'''
  # should I add SIZEOF in children
  p[0] = Node(name = 'SizeOf',val = p[3].val,lno = p[3].lno,type = p[3].type,children = [p[3]])
  p[0].ast = build_AST(p)
  # TODO: Handle 3ac

#########################

def p_unary_operator(p):
  '''unary_operator : AND
                    | MULTIPLY
                    | PLUS
                    | MINUS
                    | NOT
                    | LNOT
  '''
  p[0] = Node(name = 'UnaryOperator',val = p[1],lno = p.lineno(1),type = '',children = [], place = p[1])
  p[0].ast = build_AST(p)

#################

def p_cast_expression(p):
  '''cast_expression : unary_expression
                     | LPAREN type_name RPAREN cast_expression
  '''
  if(len(p) == 2):
    p[0] = p[1]
    p[0].ast = build_AST(p)
  else:
    # confusion about val
    tmp = get_new_tmp(p[2].type)
    p[0] = Node(name = 'TypeCasting',val = p[2].val,lno = p[2].lno,type = p[2].type,children = [], place = tmp)
    p[0].ast = build_AST(p)
    change_data_type_emit(p[4].type, p[2].type, p[4].place, p[0].place)
################

#No type should be passed in below cases since multiplication, division, add, sub work
# for all types that are present in C.

def p_multipicative_expression(p):
  '''multiplicative_expression : cast_expression
    | multiplicative_expression MULTIPLY cast_expression
    | multiplicative_expression DIVIDE cast_expression
    | multiplicative_expression MOD cast_expression
  '''
  if(len(p) == 2):
    p[0] = p[1]
    p[0].ast = build_AST(p)
  else:
    # val empty 
    if(p[1].type == '' or p[3].type == ''):
      p[0] = Node(name = 'MulDiv',val = '',lno = p[1].lno,type = 'int',children = [])
      p[0].ast = build_AST(p)
      return
    tempNode = Node(name = '',val = p[2],lno = p[1].lno,type = '',children = '')

    type_list = ['char' , 'short' , 'int' , 'long' , 'float' , 'double']
    if(p[1].type.split()[-1] not in type_list or p[3].type.split()[-1] not in type_list):
      print(p[1].lno , 'COMPILATION ERROR : Incompatible data type with ' + extract_if_tuple(p[2]) +  ' operator')

    check_invalid_operation_on_function(p[1])
    check_invalid_operation_on_function(p[3])    
    
    if(p[2] == '%'):
      valid_type = ['char' , 'short' , 'int' , 'long']
      higher_data_type = get_higher_data_type(p[1].type , p[3].type)
      
      if higher_data_type not in valid_type:
        print(p[1].lno , 'COMPILATION ERROR : Incompatible data type with MOD operator')

      return_data_type = higher_data_type
      if return_data_type == 'char' :
        return_data_type = 'int'
      p[0] = Node(name = 'Mod',val = p[1].val,lno = p[1].lno,type = return_data_type,children = [])
      p[0].ast = build_AST(p)

    else:
      higher_data_type = get_higher_data_type(p[1].type , p[3].type)
      return_data_type = higher_data_type
      if return_data_type == 'char' :
        return_data_type = 'int'
      p[0] = Node(name = 'MulDiv',val = p[1].val,lno = p[1].lno,type = return_data_type,children = [])
      p[0].ast = build_AST(p)

    # handling the emits
    p[0], p[1], p[2], p[3] = handle_binary_emit(p[0], p[1], p[2], p[3])
########
def p_additive_expression(p):
  '''additive_expression : multiplicative_expression
	| additive_expression PLUS multiplicative_expression
	| additive_expression MINUS multiplicative_expression
  '''
  if(len(p) == 2):
    p[0] = p[1]
    p[0].ast = build_AST(p)
  else:
    if(p[1].type == '' or p[3].type == ''):
      p[0] = Node(name = 'AddSub',val = '',lno = p[1].lno,type = 'int',children = [])
      p[0].ast = build_AST(p)
      return
    elif(p[1].type.endswith('*') and not (p[3].type.endswith('*'))):
      if(p[3].type == 'float'):
        print(p[1].lno , 'COMPILATION ERROR : Incompatible data type with ' + extract_if_tuple(p[2]) +  ' operator')
      p[0] = Node(name = 'AddSub',val = '',lno = p[1].lno,type = p[1].type,children = [])
      p[0].ast = build_AST(p)
    elif(p[3].type.endswith('*') and not (p[1].type.endswith('*'))):
      if(p[1].type == 'float'):
        print(p[1].lno , 'COMPILATION ERROR : Incompatible data type with ' + extract_if_tuple(p[2]) +  ' operator')
      p[0] = Node(name = 'AddSub',val = '',lno = p[1].lno,type = p[3].type,children = [])
      p[0].ast = build_AST(p)
    elif(p[1].type.endswith('*') and p[3].type.endswith('*')):
      if(p[2] == '-'):
        pass
      else:
        print(p[1].lno , 'COMPILATION ERROR : Incompatible data type with ' + extract_if_tuple(p[2]) +  ' operator')
      p[0] = Node(name = 'AddSub',val = '',lno = p[1].lno,type = p[1].type,children = [])
      p[0].ast = build_AST(p)
    else :
      type_list = ['char' , 'short' , 'int' , 'long' , 'float' , 'double']
      if p[1].type.split()[-1] not in type_list or p[3].type.split()[-1] not in type_list:
        print(p[1].lno , 'COMPILATION ERROR : Incompatible data type with ' + extract_if_tuple(p[2]) +  ' operator')
      higher_data_type = get_higher_data_type(p[1].type , p[3].type)
      p[0] = Node(name = 'AddSub',val = '',lno = p[1].lno,type = higher_data_type,children = [])
      p[0].ast = build_AST(p)
    check_invalid_operation_on_function(p[1])
    check_invalid_operation_on_function(p[3])
    
    # handling emits
    p[0], p[1], p[2], p[3] = handle_binary_emit(p[0], p[1], p[2], p[3])
    
##############


def p_shift_expression(p):
  '''shift_expression : additive_expression
	| shift_expression LSHIFT additive_expression
	| shift_expression RSHIFT additive_expression
	'''
  #p[0] = Node()
  # p[0] = build_AST(p)
  if(len(p) == 2):
    p[0] = p[1]
    p[0].ast = build_AST(p)
  else:
    if(p[1].type == '' or p[3].type == ''):
      p[0] = Node(name = 'Shift',val = '',lno = p[1].lno,type = 'int',children = [])
      p[0].ast = build_AST(p)
      return
    # We know shift only possible in int(unsigned) type, so no need to pass for now
    type_list = ['short' , 'int' , 'long']
    if p[1].type.split()[-1] not in type_list or p[3].type.split()[-1] not in type_list:
      print(p[1].lno , 'COMPILATION ERROR : Incompatible data type with ' + extract_if_tuple(p[2]) +  ' operator')

    check_invalid_operation_on_function(p[1])
    check_invalid_operation_on_function(p[3])

    higher_data_type = get_higher_data_type(p[1].type , p[3].type)
    p[0] = Node(name = 'Shift',val = '',lno = p[1].lno,type = higher_data_type,children = [])
    p[0].ast = build_AST(p)

    # handling emits
    p[0], p[1], p[2], p[3] = handle_binary_emit(p[0], p[1], p[2], p[3])

##############

def p_relational_expression(p):
  '''relational_expression : shift_expression
	| relational_expression LESS shift_expression
	| relational_expression GREATER shift_expression
	| relational_expression LESSEQUAL shift_expression
	| relational_expression GREATEREQUAL shift_expression
  '''
  #p[0] = Node()
  # p[0] = build_AST(p)
  if(len(p) == 2):
    p[0] = p[1]
    p[0].ast = build_AST(p)
  else:
    if(p[1].type == '' or p[3].type == ''):
      p[0] = Node(name = 'RelationalOperation',val = '',lno = p[1].lno,type = 'int',children = [])
      p[0].ast = build_AST(p)
      return
    if(p[1].type.endswith('*') and p[3].type.endswith('*')):
      pass
    else:
      type_list = ['char' , 'short' , 'int' , 'long' , 'float' , 'double']
      if p[1].type.split()[-1] not in type_list or p[3].type.split()[-1] not in type_list:
        print(p[1].lno , 'COMPILATION ERROR : Incompatible data type with ' + extract_if_tuple(p[2]) +  ' operator')

    check_invalid_operation_on_function(p[1])
    check_invalid_operation_on_function(p[3])

    p[0] = Node(name = 'RelationalOperation',val = '',lno = p[1].lno,type = 'int',children = [])
    p[0].ast = build_AST(p)

    # handling emits
    p[0], p[1], p[2], p[3] = handle_binary_emit(p[0], p[1], p[2], p[3])

def p_equality_expresssion(p):
  '''equality_expression : relational_expression
	| equality_expression EQUAL relational_expression
	| equality_expression NOTEQUAL relational_expression
  '''
  if(len(p) == 2):
    p[0] = p[1]
    p[0].ast = build_AST(p)
  else:
    if(p[1].type == '' or p[3].type == ''):
      p[0] = Node(name = 'EqualityOperation',val = '',lno = p[1].lno,type = 'int',children = [])
      p[0].ast = build_AST(p)
      return
    if(p[1].type.endswith('*') and p[3].type.endswith('*')):
      pass
    else:
      type_list = ['char' , 'short' , 'int' , 'long' , 'float' , 'double']
      if p[1].type.split()[-1] not in type_list or p[3].type.split()[-1] not in type_list:
        print(p[1].lno , 'COMPILATION ERROR : Incompatible data type with ' + extract_if_tuple(p[2]) +  ' operator')

    check_invalid_operation_on_function(p[1])
    check_invalid_operation_on_function(p[3])

    p[0] = Node(name = 'EqualityOperation',val = '',lno = p[1].lno,type = 'int',children = [])
    p[0].ast = build_AST(p)

    # handling emits
    p[0], p[1], p[2], p[3] = handle_binary_emit(p[0], p[1], p[2], p[3])

def p_and_expression(p):
  '''and_expression : equality_expression
	| and_expression AND equality_expression
  '''
  if(len(p) == 2):
    p[0] = p[1]
    p[0].ast = build_AST(p)
  else:
    if(p[1].type == '' or p[3].type == ''):
      p[0] = Node(name = 'AndOperation',val = '',lno = p[1].lno,type = 'int',children = [])
      p[0].ast = build_AST(p)
      return
    p[0] = Node(name = 'AndOperation',val = '',lno = p[1].lno,type = '',children = [])
    p[0].ast = build_AST(p)
    valid = ['int', 'char','long','short'] #TODO: check this if more AND should be taken

    if p[1].type.split()[-1] not in valid or p[3].type.split()[-1] not in valid:
      print(p[1].lno , 'COMPILATION ERROR : Incompatible data types', p[1].type, 'and', p[3].type, 'for the AND operator')

    check_invalid_operation_on_function(p[1])
    check_invalid_operation_on_function(p[3])
    
    p[0].type = 'int' # should not be char, even if the and was done for two chars
    # handling emits
    p[0], p[1], p[2], p[3] = handle_binary_emit(p[0], p[1], p[2], p[3])

# TODO: do the above expression things below as well

def p_exclusive_or_expression(p):
  '''exclusive_or_expression : and_expression
	| exclusive_or_expression XOR and_expression
	'''
  if(len(p) == 2):
    p[0] = p[1]
    p[0].ast = build_AST(p)
  else:
    if(p[1].type == '' or p[3].type == ''):
      p[0] = Node(name = 'XorOperation',val = '',lno = p[1].lno,type = 'int',children = [])
      p[0].ast = build_AST(p)
      return
    type_list = ['char' , 'short' , 'int' , 'long']
    if p[1].type.split()[-1] not in type_list or p[3].type.split()[-1] not in type_list:
      print(p[1].lno , 'COMPILATION ERROR : Incompatible data type with ' + extract_if_tuple(p[2]) +  ' operator')
    check_invalid_operation_on_function(p[1])
    check_invalid_operation_on_function(p[3])

    p[0] = Node(name = 'XorOperation',val = '',lno = p[1].lno,type = 'int',children = [])
    p[0].ast = build_AST(p)
    # handling emits
    p[0], p[1], p[2], p[3] = handle_binary_emit(p[0], p[1], p[2], p[3])

def p_inclusive_or_expression(p):
  '''inclusive_or_expression : exclusive_or_expression
	| inclusive_or_expression OR exclusive_or_expression
  '''
  if(len(p) == 2):
    p[0] = p[1]
    p[0].ast = build_AST(p)
  else:
    if(p[1].type == '' or p[3].type == ''):
      p[0] = Node(name = 'OrOperation',val = '',lno = p[1].lno,type = 'int',children = [])
      p[0].ast = build_AST(p)
      return
    type_list = ['char' , 'short' , 'int' , 'long']
    if p[1].type.split()[-1] not in type_list or p[3].type.split()[-1] not in type_list:
      print(p[1].lno , 'COMPILATION ERROR : Incompatible data type with ' + extract_if_tuple(p[2]) +  ' operator')
    
    check_invalid_operation_on_function(p[1])
    check_invalid_operation_on_function(p[3])

    p[0] = Node(name = 'OrOperation',val = '',lno = p[1].lno,type = 'int',children = [])
    p[0].ast = build_AST(p)
    # handling emits
    p[0], p[1], p[2], p[3] = handle_binary_emit(p[0], p[1], p[2], p[3])

def p_logical_and_expression(p):
  '''logical_and_expression : inclusive_or_expression 
  | logical_and_expression AndMark1 LAND inclusive_or_expression AndMark2
  '''
  if(len(p) == 2):
    p[0] = p[1]
    p[0].ast = build_AST(p)
  else:
    if(p[1].type == '' or p[4].type == ''):
      p[0] = Node(name = 'LogicalAndOperation',val = '',lno = p[1].lno,type = 'int',children = [])
      p[0].ast = build_AST(p)
      return
    type_list = ['char' , 'short' , 'int' , 'long','float','double']
    if p[1].type.split()[-1] not in type_list or p[4].type.split()[-1] not in type_list:
      print(p[1].lno , 'COMPILATION ERROR : Incompatible data type with ' + extract_if_tuple(p[3]) +  ' operator')

    check_invalid_operation_on_function(p[1])
    check_invalid_operation_on_function(p[4])
    
    
    # print(tmp)
    p[0] = Node(name = 'LogicalAndOperation',val = '',lno = p[1].lno,type = 'int',children = [], place = p[2][1])
    p[0].ast = build_AST(p)

def p_AndMark1(p):
  '''AndMark1 : '''
  l1 = get_label()
  l2 = get_label()
  tmp = get_new_tmp('int')
  emit('ifgoto', p[-1].place, 'neq 0', l2)
  emit('int_=', '0', '', tmp)
  emit('goto', '', '', l1)
  emit('label', '', '', l2)
  p[0] = [l1, tmp]

def p_AndMark2(p):
  '''AndMark2 : '''
  l3 = get_label()
  emit('ifgoto', p[-1].place, 'neq 0', l3)
  emit('int_=', '0', '', p[-3][1])
  emit('goto', '', '', p[-3][0])
  emit('label', '', '', l3)
  emit('int_=', '1', '', p[-3][1])
  emit('label', '', '', p[-3][0])

def p_logical_or_expression(p):
  '''logical_or_expression : logical_and_expression
	| logical_or_expression OrMark1 LOR logical_and_expression OrMark2
  '''
  if(len(p) == 2):
    p[0] = p[1]
    p[0].ast = build_AST(p)
  else:
    if(p[1].type == '' or p[4].type == ''):
      p[0] = Node(name = 'LogicalOrOperation',val = '',lno = p[1].lno,type = 'int',children = [])
      p[0].ast = build_AST(p)
      return
    type_list = ['char' , 'short' , 'int' , 'long','float','double']
    if p[1].type.split()[-1] not in type_list or p[4].type.split()[-1] not in type_list:
      print(p[1].lno , 'COMPILATION ERROR : Incompatible data type with ' + extract_if_tuple(p[3]) +  ' operator')

    check_invalid_operation_on_function(p[1])
    check_invalid_operation_on_function(p[4])


    p[0] = Node(name = 'LogicalOrOperation',val = '',lno = p[1].lno,type = 'int',children = [], place = p[2][1])
    p[0].ast = build_AST(p)

# def p_OrMark1(p):
#   '''OrMark1 : '''
#   l1 = get_label()
#   emit('ifgoto', p[-1].place, 'neq 0', l1)
#   p[0] = [l1]

# def p_OrMark2(p):
#   '''OrMark2 : '''
#   emit('label', '', '', p[-3][0])

def p_OrMark1(p):
  '''OrMark1 : '''
  l1 = get_label()
  l2 = get_label()
  tmp = get_new_tmp('int')
  emit('ifgoto', p[-1].place, 'eq 0', l2)
  emit('int_=', '1', '', tmp)
  emit('goto', '', '', l1)
  emit('label', '', '', l2)
  p[0] = [l1, tmp]

def p_OrMark2(p):
  '''OrMark2 : '''
  l3 = get_label()
  emit('ifgoto', p[-1].place, 'eq 0', l3)
  emit('int_=', '1', '', p[-3][1])
  emit('goto', '', '', p[-3][0])
  emit('label', '', '', l3)
  emit('int_=', '0', '', p[-3][1])
  emit('label', '', '', p[-3][0])

# TODO: everything for conditional_expression
def p_conditional_expression(p):
  '''conditional_expression : logical_or_expression
	| logical_or_expression CondMark1 CONDOP expression COLON CondMark2 conditional_expression CondMark3
  '''
  if(len(p) == 2):
    p[0] = p[1]
    p[0].ast = build_AST(p)
  else:
    p[0] = Node(name = 'ConditionalOperation',val = '',lno = p[1].lno,type = p[4].type,children = [], place = p[2][1])
    p[0].ast = build_AST(p)
  

def p_CondMark1(p):
  '''CondMark1 : '''
  l1 = get_label()
  tmp = get_new_tmp('')
  emit('ifgoto', p[-1].place, 'eq 0', l1)
  p[0] = [l1, tmp]

def p_CondMark2(p):
  '''CondMark2 : '''
  l2 = get_label()
  # p[-4][1].type = int_or_real(p[-2].type)
  symbol_table[0][p[-4][1]]['type'] = int_or_real(p[-2].type)
  symbol_table[0][p[-4][1]]['size'] = get_data_type_size(int_or_real(p[-2].type))
  emit(int_or_real(p[-2].type) + '_=', p[-2].place, '', p[-4][1])
  emit('goto', '', '', l2)
  emit('label', '', '', p[-4][0])
  p[0] = [l2]

def p_CondMark3(p):
  '''CondMark3 : '''
  symbol_table[0][p[-6][1]]['type'] = int_or_real(p[-1].type)
  symbol_table[0][p[-6][1]]['size'] = get_data_type_size(int_or_real(p[-1].type))
  emit(int_or_real(p[-1].type) + '_=', p[-1].place, '', p[-6][1])
  emit('label', '', '', p[-2][0])

def p_assignment_expression(p):
  '''assignment_expression : conditional_expression
                           | unary_expression assignment_operator assignment_expression
  '''
  if(len(p) == 2):
    p[0] = p[1]
    p[0].ast = build_AST(p)
  else:
    if(p[1].type == '' or p[3].type == ''):
      p[0] = Node(name = 'AssignmentOperation',val = '',lno = p[1].lno,type = 'int',children = [])
      p[0].ast = build_AST(p)
      return
    if p[1].type == '-1' or p[3].type == '-1':
      return
    if('const' in p[1].type.split()):
      print('Error, modifying a variable declared with const keyword at line ' + str(p[1].lno))
    if('struct' in p[1].type.split() and 'struct' not in p[3].type.split()):
      print('COMPILATION ERROR at line ' + str(p[1].lno) + ', cannot assign variable of type ' + p[3].type + ' to ' + p[1].type)
    elif('struct' not in p[1].type.split() and 'struct' in p[3].type.split()):
      print('COMPILATION ERROR at line ' + str(p[1].lno) + ', cannot assign variable of type ' + p[3].type + ' to ' + p[1].type)
    elif(p[1].type.split()[-1] != p[3].type.split()[-1]):
      print('Warning at line ' + str(p[1].lno) + ': type mismatch in assignment')
    tempScope = find_scope(p[1].val, p.lineno(1))
    if(p[1].level != p[3].level):
      print("COMPILATION ERROR at line ", str(p[1].lno), ", type mismatch in assignment")
    if(p[1].level != 0 or p[3].level != 0):
      print("COMPILATION ERROR at line ", str(p[1].lno), ", cannot assign array pointer")
    if(len(p[1].parentStruct) > 0):
      found_scope = find_scope(p[1].parentStruct , p[1].lno)
      for curr_list in symbol_table[found_scope][p[1].parentStruct]['field_list']:
        if curr_list[1] == p[1].val:
          if(len(curr_list) < 5 and len(p[1].array) == 0):
            break
          if(len(curr_list) < 5 or (len(curr_list[4]) < len(p[1].array))):
            print("COMPILATION ERROR at line ", str(p[1].lno), ", incorrect number of dimensions")
    check_invalid_operation_on_function(p[1])
    check_invalid_operation_on_function(p[3])

    if p[2].val != '=':
      if ('struct' in p[1].type.split()) or ('struct' in p[3].type.split()):
        print("Compilation Error at line", str(p[1].lno), ":Invalid operation on", p[1].val)
    
    p[0] = Node(name = 'AssignmentOperation',val = '',type = p[1].type, lno = p[1].lno, children = [], level = p[1].level)
    p[0].ast = build_AST(p)
    if p[2].val == '=':
      operator = '='
      data_type = int_or_real(p[1].type)
      if (int_or_real(p[3].type) != data_type):
        tmp = get_new_tmp(data_type)
        change_data_type_emit(p[3].type, data_type, p[3].place, tmp)
        if(len(p[1].addr) == 0  ):
          emit(data_type + '_' + operator, tmp, '', p[1].place)
        else:
          emit(data_type + '_' + operator, tmp, '*', p[1].addr)
      else:
        if(len(p[1].addr) == 0  ):
          emit(int_or_real(p[1].type) + '_' + operator, p[3].place, '', p[1].place)
        else:
          emit(int_or_real(p[1].type) + '_' + operator, p[3].place, '*', p[1].addr)
    else:
      operator = p[2].val[:-1]
      higher_data_type = int_or_real(get_higher_data_type(p[1].type , p[3].type))
      if (int_or_real(p[1].type) != higher_data_type):
        tmp = get_new_tmp(higher_data_type)
        change_data_type_emit(p[1].type, higher_data_type, p[1].place, tmp)
        emit(higher_data_type + '_' + operator, tmp, p[3].place, tmp)
        change_data_type_emit(higher_data_type, p[1].type, tmp, p[1].place)
      elif (int_or_real(p[3].type) != higher_data_type):
        tmp = get_new_tmp(higher_data_type)
        change_data_type_emit(p[3].type, higher_data_type, p[3].place, tmp)
        emit(higher_data_type + '_' + operator, p[1].place, tmp, p[1].place)
      else:
        emit(int_or_real(p[1].type) + '_' + operator, p[1].place, p[3].place, p[1].place)
        
    p[0].place = p[1].place


def p_assignment_operator(p):
  '''assignment_operator : EQUALS
	| MULTIPLYEQUAL
	| DIVIDEEQUAL
	| MODEQUAL
	| PLUSEQUAL
	| MINUSEQUAL
	| LSHIFTEQUAL
	| RSHIFTEQUAL
	| ANDEQUAL
	| XOREQUAL
	| OREQUAL
	'''
  p[0] = Node(name = 'AssignmentOperator',val = p[1],type = '', lno = p.lineno(1), children = [p[1]])
  p[0].ast = build_AST(p)

def p_expression(p):
  '''expression : assignment_expression
	| expression COMMA assignment_expression
  '''
  if(len(p) == 2):
    p[0] = p[1]
    p[0].ast = build_AST(p)
  else:
    # optimized here, might also be possible above somewhere
    p[0] = p[1]
    p[0].children.append(p[3])
    p[0].ast = build_AST(p)

def p_constant_expression(p):
  '''constant_expression : conditional_expression'''
  p[0] = p[1]
  p[0].ast = build_AST(p)

def p_temp_declaration(p):
  '''temp_declaration : declaration_specifiers init_declarator_list'''
  global currentScope
  if(p[2].isFunc > 0):
    currentScope = parent[currentScope]
    print(currentScope)
  # a = 1
  p[0] = Node(name = 'Declaration',val = p[1],type = p[1].type, lno = p.lineno(1), children = [])
  p[0].ast = build_AST(p)
  flag = 1
  if('void' in p[1].type.split()):
    flag = 0
  for child in p[2].children:

    if(child.name == 'InitDeclarator'):
      if(p[1].type.startswith('typedef')):
        print("COMPILATION ERROR at line " + str(p[1].lno) + ": typedef intialized")
        continue
      if(child.children[0].val in symbol_table[currentScope].keys()):
        print(p.lineno(1), 'COMPILATION ERROR : ' + child.children[0].val + ' already declared')
      symbol_table[currentScope][child.children[0].val] = {}
      symbol_table[currentScope][child.children[0].val]['type'] = p[1].type
      symbol_table[currentScope][child.children[0].val]['value'] = child.children[1].val
      symbol_table[currentScope][child.children[0].val]['size'] = get_data_type_size(p[1].type)
      symbol_table[currentScope][child.children[0].val]['offset'] = offset[currentScope]
      totalEle = 1
      act_data_type=p[1].type
      if(len(child.children[0].array) > 0):
        symbol_table[currentScope][child.children[0].val]['array'] = child.children[0].array
        for i in child.children[0].array:
          totalEle = totalEle*i
      if(len(child.children[0].type) > 0):
        act_data_type = p[1].type + ' ' + child.children[0].type
        symbol_table[currentScope][child.children[0].val]['type'] = act_data_type 
        symbol_table[currentScope][child.children[0].val]['size'] = 8
      elif(flag == 0):
        print("COMPILATION ERROR at line " + str(p[1].lno) + ", variable " + child.children[0].val + " cannot have type void")
      symbol_table[currentScope][child.children[0].val]['size'] *= totalEle
      offset[currentScope] += symbol_table[currentScope][child.children[0].val]['size']

      # 3AC Code 
      child.children[0].place = child.children[0].val + '_' + str(currentScope)
      # print(child.children[1].val)
      operator = '='
      data_type = int_or_real(act_data_type)
      if data_type == 'pointer' and int_or_real(child.children[1].type) != 'pointer':
        print("COMPILATION ERROR at line " + str(p[1].lno) + ", variable " + child.children[1].val + " is not a pointer")
      elif (int_or_real(child.children[1].type) != data_type):
        tmp = get_new_tmp(data_type)
        change_data_type_emit(child.children[1].type, data_type, child.children[1].place, tmp)
        emit(data_type + '_' + operator, tmp, '', child.children[0].place)
      else:
        emit(data_type + '_' + operator, child.children[1].place, '', child.children[0].place)
    else:
      if(child.val in symbol_table[currentScope].keys() and 'isFunc' in symbol_table[currentScope][child.val]):
        continue
      if(child.val in symbol_table[currentScope].keys() and 'isFunc' not in symbol_table[currentScope][child.val]):
        print(p.lineno(1), 'COMPILATION ERROR : ' + child.val + ' already declared')
      symbol_table[currentScope][child.val] = {}
      symbol_table[currentScope][child.val]['type'] = p[1].type
      symbol_table[currentScope][child.val]['size'] = get_data_type_size(p[1].type)
      symbol_table[currentScope][child.val]['offset'] = offset[currentScope]
      totalEle = 1
      if(len(child.array) > 0):
        symbol_table[currentScope][child.val]['array'] = child.array
        for i in child.array:
          totalEle = totalEle*i
      if(len(child.type) > 0):
        symbol_table[currentScope][child.val]['type'] = p[1].type + ' ' + child.type
        symbol_table[currentScope][child.val]['size'] = 8
      elif(flag == 0):
        print("COMPILATION ERROR at line " + str(p[1].lno) + ", variable " + child.val + " cannot have type void")
      symbol_table[currentScope][child.val]['size'] *= totalEle
      offset[currentScope] += symbol_table[currentScope][child.val]['size']
      # TODO : Confirm with others about two possible approaches
      # if(p[1].type.startswith('struct')):
      #   found_scope = find_if_ID_is_declared(p[1].type, p.lineno(1))
      #   if found_scope != -1:
      #     symbol_table[currentScope][child.val]['field_list'] = symbol_table[found_scope][p[1].type]['field_list']

  if p[1].type.startswith('typedef'):
    keywords[p[2].children[0].val] = keywords[p[1].type.split()[-1]]
    print(p[2].children[0].val, p[1].type.split()[-1])

def p_declaration(p):
  '''declaration : declaration_specifiers SEMICOLON
	| temp_declaration SEMICOLON
  '''
  
  if(len(p) == 3):
    
    # if(p[2].isFunc > 0):
    #   currentScope = parent[currentScope]
    #   print(currentScope)
    p[0] = p[1]
    p[0].ast = build_AST(p)
  # else:
    # if p[1].type.startswith('typedef'):
    #   keywords[p[2].children[0].val] = keywords[p[1].type.split()[-1]]
    # # print('here')
    # if(p[2].isFunc > 0):
    #   currentScope = parent[currentScope]
    #   print(currentScope)
    # # a = 1
    # p[0] = Node(name = 'Declaration',val = p[1],type = p[1].type, lno = p.lineno(1), children = [])
    # p[0].ast = build_AST(p)
    # flag = 1
    # if('void' in p[1].type.split()):
    #   flag = 0
    # for child in p[2].children:

    #   if(child.name == 'InitDeclarator'):
    #     if(p[1].type.startswith('typedef')):
    #       print("COMPILATION ERROR at line " + str(p[1].lno) + ": typedef intialized")
    #       continue
    #     if(child.children[0].val in symbol_table[currentScope].keys()):
    #       print('here1')
    #       print(p.lineno(1), 'COMPILATION ERROR : ' + child.children[0].val + ' already declared')
    #     symbol_table[currentScope][child.children[0].val] = {}
    #     symbol_table[currentScope][child.children[0].val]['type'] = p[1].type
    #     symbol_table[currentScope][child.children[0].val]['value'] = child.children[1].val
    #     symbol_table[currentScope][child.children[0].val]['size'] = get_data_type_size(p[1].type)
    #     symbol_table[currentScope][child.children[0].val]['offset'] = offset[currentScope]
    #     totalEle = 1
    #     if(len(child.children[0].array) > 0):
    #       symbol_table[currentScope][child.children[0].val]['array'] = child.children[0].array
    #       for i in child.children[0].array:
    #         totalEle = totalEle*i
    #     if(len(child.children[0].type) > 0):
    #       symbol_table[currentScope][child.children[0].val]['type'] = p[1].type + ' ' + child.children[0].type 
    #       symbol_table[currentScope][child.children[0].val]['size'] = 8
    #     elif(flag == 0):
    #       print("COMPILATION ERROR at line " + str(p[1].lno) + ", variable " + child.children[0].val + " cannot have type void")
    #     symbol_table[currentScope][child.children[0].val]['size'] *= totalEle
    #     offset[currentScope] += symbol_table[currentScope][child.children[0].val]['size']
    #     # 3AC Code 
    #     child.children[0].place = child.children[0].val
    #     # print(child.children[1].val)
    #     operator = '='
    #     data_type = int_or_real(p[1].type)
    #     if (int_or_real(child.children[1].type) != data_type):
    #       tmp = get_new_tmp(data_type)
    #       change_data_type_emit(child.children[1].type, data_type, child.children[1].place, tmp)
    #       emit(data_type + '_' + operator, tmp, '', child.children[0].place)
    #     else:
    #       emit(int_or_real(p[1].type) + '_' + operator, child.children[1].place, '', child.children[0].place)
    #   else:
    #     if(child.val in symbol_table[currentScope].keys() and 'isFunc' in symbol_table[currentScope][child.val]):
    #       continue
    #     if(child.val in symbol_table[currentScope].keys() and 'isFunc' not in symbol_table[currentScope][child.val]):
    #       print(p.lineno(1), 'COMPILATION ERROR : ' + child.val + ' already declared')
    #     symbol_table[currentScope][child.val] = {}
    #     symbol_table[currentScope][child.val]['type'] = p[1].type
    #     symbol_table[currentScope][child.val]['size'] = get_data_type_size(p[1].type)
    #     symbol_table[currentScope][child.val]['offset'] = offset[currentScope]
    #     totalEle = 1
    #     if(len(child.array) > 0):
    #       symbol_table[currentScope][child.val]['array'] = child.array
    #       for i in child.array:
    #         totalEle = totalEle*i
    #     if(len(child.type) > 0):
    #       symbol_table[currentScope][child.val]['type'] = p[1].type + ' ' + child.type
    #       symbol_table[currentScope][child.val]['size'] = 8
    #     elif(flag == 0):
    #       print("COMPILATION ERROR at line " + str(p[1].lno) + ", variable " + child.val + " cannot have type void")
    #     symbol_table[currentScope][child.val]['size'] *= totalEle
    #     offset[currentScope] += symbol_table[currentScope][child.val]['size']
    #     # TODO : Confirm with others about two possible approaches
    #     # if(p[1].type.startswith('struct')):
    #     #   found_scope = find_if_ID_is_declared(p[1].type, p.lineno(1))
    #     #   if found_scope != -1:
    #     #     symbol_table[currentScope][child.val]['field_list'] = symbol_table[found_scope][p[1].type]['field_list']


# TODO : change the below to support long, short etc.
def p_declaration_specifiers(p):
  '''declaration_specifiers : storage_class_specifier
	| storage_class_specifier declaration_specifiers
	| type_specifier
	| type_specifier declaration_specifiers
	| type_qualifier
	| type_qualifier declaration_specifiers
  '''
  # TypeQualifier, TypeSpecifier1, StorageClassSpecifier
  if(len(p) == 2):
    p[0] = p[1]
    p[0].ast = build_AST(p)
    # global curFuncReturnType
    curType.append(p[1].type)
  elif(len(p) == 3):
    if(p[1].name == 'StorageClassSpecifier' and p[2].name.startswith('StorageClassSpecifier')):
      print("Invalid Syntax at line " + str(p[1].lno) + ", " + p[2].type + " not allowed after " + p[1].type)
    if(p[1].name == 'TypeSpecifier1' and (p[2].name.startswith('TypeSpecifier1') or p[2].name.startswith('StorageClassSpecifier') or p[2].name.startswith('TypeQualifier'))):
      print("Invalid Syntax at line " + str(p[1].lno) + ", " + p[2].type + " not allowed after " + p[1].type)
    if(p[1].name == 'TypeQualifier' and (p[2].name.startswith('StorageClassSpecifier') or p[2].name.startswith('TypeQualifier'))):
      print("Invalid Syntax at line " + str(p[1].lno) + ", " + p[2].type + " not allowed after " + p[1].type)
    curType.pop()
    curType.append(p[1].type + ' ' + p[2].type)
    
    ty = ""
    if len(p[1].type) > 0:
      ty = p[1].type + ' ' + p[2].type
    else:
      ty = p[2].type
    curType.append(ty)
    # print(ty)
    p[0] = Node(name = p[1].name + p[2].name,val = p[1],type = ty, lno = p[1].lno, children = [])
    p[0].ast = build_AST(p)


def p_init_declarator_list(p):
  '''init_declarator_list : init_declarator
	| init_declarator_list COMMA init_declarator
  '''
  if(len(p) == 2):
    p[0] = Node(name = 'InitDeclaratorList', val = '', type = '', lno = p.lineno(1), children = [p[1]],isFunc=p[1].isFunc)
    p[0].ast = build_AST(p)
  else:
    #check once
    p[0] = p[1]
    p[0].children.append(p[3])
    p[0].ast = build_AST(p)

def p_init_declarator(p):
  '''init_declarator : declarator
	| declarator EQUALS initializer
  '''
  if(len(p) == 2):
    # extra node might be needed for error checking
    #maybe make different function to do this
    p[0] = p[1]
    p[0].ast = build_AST(p)
  else:
    p[0] = Node(name = 'InitDeclarator',val = '',type = p[1].type,lno = p.lineno(1), children = [p[1],p[3]], array = p[1].array,isFunc=p[1].isFunc)
    p[0].ast = build_AST(p)
    if(len(p[1].array) > 0 and (p[3].maxDepth == 0 or p[3].maxDepth > len(p[1].array))):
      print('COMPILATION ERROR at line ' + str(p.lineno(1)) + ' , invalid initializer')
    if(p[1].level != p[3].level):
      print("COMPILATION ERROR at line ", str(p[1].lno), ", type mismatch")
    # print(p[3].name, "fn name:p_init_declarator")
    # emit(["=",[p[3].place, ], [], [p[1].place], find_scope(p[1].val)]) # a = 5 ,  a = t1

def p_storage_class_specifier(p):
  '''storage_class_specifier : TYPEDEF
	| EXTERN
	| STATIC
	| AUTO
	| REGISTER
  '''
  p[0] = Node(name = 'StorageClassSpecifier',val = '',type = p[1], lno = p.lineno(1), children = [])


def p_type_specifier_1(p):
  '''type_specifier : VOID
                    | CHAR
                    | SHORT
                    | INT
                    | LONG
                    | FLOAT
                    | DOUBLE
                    | SIGNED
                    | UNSIGNED
                    | TYPE_NAME
  '''
  p[0] = Node(name = 'TypeSpecifier1',val = '',type = p[1], lno = p.lineno(1), children = [])

def p_type_specifier_2(p):
  '''type_specifier : struct_or_union_specifier
                    | enum_specifier '''
  p[0] = p[1]
  p[0].ast = build_AST(p)

def p_struct_or_union_specifier(p):
  '''struct_or_union_specifier : struct_or_union ID openbrace struct_declaration_list closebrace
  | struct_or_union openbrace struct_declaration_list closebrace
  | struct_or_union ID
  '''
  # TODO : check the semicolon thing after closebrace in grammar
  # TODO : Manage the size and offset of fields
  p[0] = Node(name = 'StructOrUnionSpecifier', val = '', type = '', lno = p[1].lno , children = [])
  if len(p) == 6:
    val_name = p[1].type + ' ' + p[2]
    p[0].ast = build_AST(p)
    if val_name in symbol_table[currentScope].keys():
      print('COMPILATION ERROR : near line ' + str(p[1].lno) + ' struct already declared')
    valptr_name = val_name + ' *'
    symbol_table[currentScope][val_name] = {}
    symbol_table[currentScope][val_name]['type'] = val_name
    symbol_table[currentScope][valptr_name] = {}
    symbol_table[currentScope][valptr_name]['type'] = valptr_name
    temp_list = []
    curr_offset = 0
    max_size = 0
    for child in p[4].children:
      for prev_list in temp_list:
        if prev_list[1] == child.val:
          print('COMPILATION ERROR : line ' + str(p[4].lno) + ' : ' + child.val + ' already deaclared')
      if get_data_type_size(child.type) == -1:
        print("COMPILATION ERROR at line " + str(child.lno) + " : data type not defined")
      SZ = get_data_type_size(child.type)
      curr_list = [child.type, child.val, SZ, curr_offset]
      totalEle = 1
      if(len(child.array) > 0):
        curr_list.append(child.array)
        for ele in child.array:
          totalEle *= ele
      curr_offset = curr_offset + get_data_type_size(child.type)*totalEle
      curr_list[2] *= totalEle
      SZ *= totalEle
      max_size = max(max_size , SZ)
      if p[1].type == 'union':
        curr_list[3] = 0
      temp_list.append(curr_list)

    if p[1].type == 'union':
      curr_offset = max_size
    symbol_table[currentScope][val_name]['field_list'] = temp_list
    symbol_table[currentScope][val_name]['size'] = curr_offset
    symbol_table[currentScope][valptr_name]['field_list'] = temp_list
    symbol_table[currentScope][valptr_name]['size'] = 8

  elif len(p) == 3:
    p[0].type = p[1].type + ' ' + p[2]
    p[0].ast = build_AST(p)
    found_scope = find_scope(p[0].type, p[1].lno)
    if(found_scope == -1):
      print("COMPILATION ERROR : at line " + str(p[1].lno) + ", " + p[0].type + " is not a type")
  else:
    p[0].ast = build_AST(p)


def p_struct_or_union(p):
  '''struct_or_union : STRUCT
	| UNION
  '''
  if p[1] == 'struct':
    p[0] = Node(name = 'StructOrUNion', val = '', type = 'struct', lno = p.lineno(1), children = [])
    p[0].ast = build_AST(p)
  else:
    p[0] = Node(name = 'StructOrUNion', val = '', type = 'union', lno = p.lineno(1), children = [])
    p[0].ast = build_AST(p)

def p_struct_declaration_list(p):
  '''struct_declaration_list : struct_declaration
	| struct_declaration_list struct_declaration
  '''
  p[0] = Node(name = 'StructDeclarationList', val = '', type = p[1].type, lno = p[1].lno, children = [])
  p[0].ast = build_AST(p)
  if(len(p) == 2):
    p[0].children = p[1].children
  else:
    p[0].children = p[1].children
    p[0].children.extend(p[2].children)


def p_struct_declaration(p):
  '''struct_declaration : specifier_qualifier_list struct_declarator_list SEMICOLON
  '''
  p[0] = Node(name = 'StructDeclaration', val = '', type = p[1].type, lno = p[1].lno, children = [])
  p[0].ast = build_AST(p)
  p[0].children = p[2].children
  for child in p[0].children:
    if len(child.type) > 0:
      child.type = p[1].type + ' ' + child.type
    else:
      if('void' in p[1].type.split()):
        print("COMPILATION ERROR at line " + str(p[1].lno) + ", variable " + child.val + " cannot have type void")
      child.type = p[1].type

def p_specifier_qualifier_list(p):
  '''specifier_qualifier_list : type_specifier specifier_qualifier_list
  | type_specifier
  | type_qualifier specifier_qualifier_list
  | type_qualifier
  '''
  p[0] = Node(name = 'SpecifierQualifierList', val = '', type = p[1].type, lno = p[1].lno, children = [])
  p[0].ast = build_AST(p)

def p_struct_declarator_list(p):
  '''struct_declarator_list : struct_declarator
	| struct_declarator_list COMMA struct_declarator
  '''
  p[0] = Node(name = 'StructDeclaratorList', val = '', type = p[1].type, lno = p[1].lno, children = [])
  if(len(p) == 2):
    p[0].children.append(p[1])
    p[0].ast = build_AST(p)
  else:
    p[0].children = p[1].children 
    p[0].children.append(p[3])
    p[0].ast = build_AST(p)

def p_struct_declarator(p):  
  '''struct_declarator : declarator
	| COLON constant_expression
	| declarator COLON constant_expression
  '''
  if len(p) == 2 or len(p) == 4:
    p[0] = p[1] 
    p[0].ast = build_AST(p)
  if len(p) == 3:
    p[0] = p[2]
    p[0].ast = build_AST(p)

def p_enum_specifier(p):
  '''enum_specifier : ENUM openbrace enumerator_list closebrace
	| ENUM ID openbrace enumerator_list closebrace
	| ENUM ID
  '''
  if(len(p) == 5):
    p[0] = Node(name = 'EnumSpecifier', val = '', type = 'Enum_Specifier', lno = p[3].lno, children = [])
    p[0].ast = build_AST(p)
  elif(len(p) == 6):
    p[0] = Node(name = 'EnumSpecifier', val = '', type = 'Enum_Specifier', lno = p[4].lno, children = [])
    p[0].ast = build_AST(p)
  else:
    p[0] = Node(name = 'EnumSpecifier', val = '', type = 'Enum_Specifier', lno = p[2].lno, children = [])
    p[0].ast = build_AST(p)

def p_enumerator_list(p):
  '''enumerator_list : enumerator
	| enumerator_list COMMA enumerator
  '''
  p[0] = Node(name = 'EnumeratorList', val= '', type = p[1].type, lno = p[1].lno, children = [])
  p[0].ast = build_AST(p)
  if(len(p) == 2):
    p[0].children.append(p[1])
  else:
    p[0].children.append(p[3])

def p_enumerator(p):
  '''enumerator : ID
	| ID EQUALS constant_expression
	'''
  p[0] = Node(name = 'Enumerator', val = '', type = '', lno = p.lineno(1), children = [])
  p[0].ast = build_AST(p)

def p_type_qualifier(p):
  '''type_qualifier : CONST
                    | VOLATILE
  '''
  p[0] = Node(name = 'TypeQualifier', val = '', type = p[1], lno = p.lineno(1), children = [])

def p_declarator(p):
  '''declarator : pointer direct_declarator
  | direct_declarator
  '''
  global curFuncReturnType
  if(len(p) == 2):
    p[0] = p[1]
    p[0].name = 'Declarator'
    p[0].val = p[1].val
    p[0].array = p[1].array
    p[0].ast = build_AST(p)
  else:
    p[0] = p[2]
    p[0].name = 'Declarator'
    p[0].type = p[1].type
    p[0].ast = build_AST(p)
    if(p[2].val in symbol_table[parent[currentScope]] and 'isFunc' in symbol_table[parent[currentScope]][p[2].val].keys()):
      symbol_table[parent[currentScope]][p[2].val]['type'] = symbol_table[parent[currentScope]][p[2].val]['type'] + ' ' + p[1].type
      curFuncReturnType = curFuncReturnType + ' ' + p[1].type
    p[0].val = p[2].val
    p[0].array = p[2].array

def p_direct_declarator_1(p):
  '''direct_declarator : ID
                        | LPAREN declarator RPAREN
                        | direct_declarator lopenparen parameter_type_list RPAREN
                        | direct_declarator lopenparen identifier_list RPAREN
  '''
  global curFuncReturnType
  if(len(p) == 2):
    p[0] = Node(name = 'ID', val = p[1], type = '', lno = p.lineno(1), children = [])
    p[0].ast = build_AST(p)

  elif(len(p) == 4):
    p[0] = p[2]
    p[0].ast = build_AST(p)
  else:
    p[0] = p[1]
    p[0].ast = build_AST(p)
    p[0].children = p
  if(len (p) == 5 and p[3].name == 'ParameterList'):
    func_arguments[p[1].val] = []
    for child in p[3].children:
      func_arguments[p[1].val].append(child.val)
    # print(func_arguments[p[1].val])
      # print(child.val)
    p[0].children = p[3].children
    p[0].type = curType[-1]
    if(p[1].val in symbol_table[parent[currentScope]].keys()):
      if('isFunc' not in symbol_table[0][p[1].val] or symbol_table[0][p[1].val]['isFunc'] == 1):
        # print(symbol_table[parent[currentScope]][p[1].val]['isFunc'])
        # print(symbol_table[parent[currentScope]][p[1].val])
        print('COMPILATION ERROR : near line ' + str(p[1].lno) + ' function already declared')
      else:
        if(p[1].val in functionScope.keys()):
          scope_to_function.pop(functionScope[p[1].val])
        functionScope[p[1].val] = currentScope
        scope_to_function[currentScope] = p[1].val
        local_vars[p[1].val] = []
        iterator = 0
        for child in p[3].children:
          if(child.type != symbol_table[0][p[1].val]['argumentList'][iterator]):
            print('COMPILATION ERROR : near line ' + str(p[1].lno) + ' argument ' + str(iterator+1) +' does not match function declaration')
          iterator += 1
      return 
    symbol_table[parent[currentScope]][p[1].val] = {}
    
    symbol_table[parent[currentScope]][p[1].val]['isFunc'] = 2
    p[0].isFunc = 2
    tempList = []
    for child in p[3].children:
      tempList.append(child.type)
    symbol_table[parent[currentScope]][p[1].val]['argumentList'] = tempList
    symbol_table[parent[currentScope]][p[1].val]['type'] = curType[-1-len(tempList)]
    curFuncReturnType = copy.deepcopy(curType[-1-len(tempList)])
    if(p[1].val in functionScope.keys()):
      scope_to_function.pop(functionScope[p[1].val])
    functionScope[p[1].val] = currentScope
    scope_to_function[currentScope] = p[1].val
    local_vars[p[1].val] = []
    # emit('func', '', '', p[1].val)


def p_direct_declarator_2(p):
  '''direct_declarator : direct_declarator LSQUAREBRACKET INT_CONST RSQUAREBRACKET'''
  p[0] = Node(name = 'ArrayDeclarator', val = p[1].val, type = '', lno = p.lineno(1),  children = [])
  p[0].ast = build_AST(p)
  p[0].array = copy.deepcopy(p[1].array)
  p[0].array.append(int(p[3][0]))

def p_direct_declarator_3(p):
  '''direct_declarator : direct_declarator LSQUAREBRACKET RSQUAREBRACKET
                        | direct_declarator lopenparen RPAREN'''
  p[0] = p[1]
  if(p[3] == ')'):
    p[0].ast = build_AST(p)
  else:
    p[0].ast = build_AST(p)  
  global curFuncReturnType
  if(p[3] == ')'):
    func_arguments[p[1].val] = []
    if(p[1].val in symbol_table[parent[currentScope]].keys()):
      # print('check')
      if('isFunc' not in symbol_table[0][p[1].val] or symbol_table[0][p[1].val]['isFunc'] == 1):
        print('COMPILATION ERROR : near line ' + str(p[1].lno) + ' function already declared')
      else:
        if(p[1].val in functionScope.keys()):
          scope_to_function.pop(functionScope[p[1].val])
        functionScope[p[1].val] = currentScope
        scope_to_function[currentScope] = p[1].val
        local_vars[p[1].val] = []
      return 
    symbol_table[parent[currentScope]][p[1].val] = {}
    symbol_table[parent[currentScope]][p[1].val]['type'] = curType[-1]
    curFuncReturnType = copy.deepcopy(curType[-1])
    symbol_table[parent[currentScope]][p[1].val]['isFunc'] = 2
    p[0].isFunc = 2
    symbol_table[parent[currentScope]][p[1].val]['argumentList'] = []
    if(p[1].val in functionScope.keys()):
      scope_to_function.pop(functionScope[p[1].val])
    functionScope[p[1].val] = currentScope
    scope_to_function[currentScope] = p[1].val
    local_vars[p[1].val] = []
    print(symbol_table[parent[currentScope]][p[1].val],p[1].val,parent[currentScope])
    # emit('func', '', '', p[1].val)

def p_pointer(p):
  '''pointer : MULTIPLY 
              | MULTIPLY type_qualifier_list
              | MULTIPLY pointer
              | MULTIPLY type_qualifier_list pointer
  '''
  if(len(p) == 2):
    p[0] = Node(name = 'Pointer',val = '',type = '*', lno = p.lineno(1), children = [])
    p[0].ast = build_AST(p)
  elif(len(p) == 3):
    p[0] = Node(name = 'Pointer',val = '',type = p[2].type + ' *', lno = p.lineno(1), children = [])
    p[0].ast = build_AST(p)
  else:
    p[0] = Node(name = 'Pointer',val = '',type = p[2].type + ' *', lno = p[2].lno, children = [])
    p[0].ast = build_AST(p)

def p_type_qualifier_list(p):
  '''type_qualifier_list : type_qualifier
                        | type_qualifier_list type_qualifier
  '''
  if(len(p) == 2):
    p[0] = p[1]
    p[0].name = 'TypeQualifierList'
    p[0].children = p[1]
    p[0].ast = build_AST(p)
  else:
    p[0] = p[1]
    p[0].children.append(p[2])
    p[0].type = p[1].type + " " + p[2].type
    p[0].name = 'TypeQualifierList'
    p[0].ast = build_AST(p)

def p_parameter_type_list(p):
  '''parameter_type_list : parameter_list
                          | parameter_list COMMA ELLIPSIS
  '''
  p[0] = p[1]
  p[0].ast = build_AST(p)


def p_parameter_list(p):
    '''parameter_list : parameter_declaration
                      | parameter_list COMMA parameter_declaration
    '''
    p[0] = Node(name = 'ParameterList', val = '', type = '', children = [], lno = p.lineno(1))
    if(len(p) == 2):
      p[0].ast = build_AST(p)
      p[0].children.append(p[1])
    else:
      p[0].ast = build_AST(p)
      p[0].children = p[1].children
      p[0].children.append(p[3])

def p_parameter_declaration(p):
    '''parameter_declaration : declaration_specifiers declarator
                             | declaration_specifiers abstract_declarator
                             | declaration_specifiers
    '''
    if(len(p) == 2):
      p[0] = p[1]
      p[0].ast = build_AST(p)
      p[0].name = 'ParameterDeclaration'
    else:
      p[0] = Node(name = 'ParameterDeclaration',val = p[2].val,type = p[1].type, lno = p[1].lno, children = [])
      p[0].ast = build_AST(p)
      if(len(p[2].type) > 0):
        p[0].type = p[1].type + ' ' + p[2].type
    if(len(p) > 2 and p[2].name == 'Declarator'):
      if(p[2].val in symbol_table[currentScope].keys()):
        print(p.lineno(1), 'COMPILATION ERROR : ' + p[2].val + ' parameter already declared')
      symbol_table[currentScope][p[2].val] = {}
      symbol_table[currentScope][p[2].val]['type'] = p[1].type

      if(len(p[2].type) > 0):
        symbol_table[currentScope][p[2].val]['type'] = p[1].type + ' ' + p[2].type
        symbol_table[currentScope][p[2].val]['size'] = get_data_type_size(p[1].type+ ' ' + p[2].type)
      else:
        if('void' in p[1].type.split()):
          print("COMPILATION ERROR at line " + str(p[1].lno) + ", parameter " + p[2].val + " cannot have type void")
        symbol_table[currentScope][p[2].val]['size'] = get_data_type_size(p[1].type)
      if(len(p[2].array) > 0):
        symbol_table[currentScope][p[2].val]['array'] = p[2].array

      symbol_table[currentScope][p[2].val]['offset'] = offset[currentScope]
      #have assumed that paramters of a function can be pointer or basics data types only
      offset[currentScope] += symbol_table[currentScope][p[2].val]['size']


def p_identifier_list(p):
    '''identifier_list : ID
                       | identifier_list COMMA ID
    '''
    if(len(p) == 2):
      p[0] = Node(name = 'IdentifierList',val = p[1],type = '', lno = p.lineno(1), children = [p[1]])
      p[0].ast = build_AST(p)
    else:
      p[0] = p[1]
      p[0].children.append(p[3])
      p[0].name = 'IdentifierList'
      p[0].ast = build_AST(p)

def p_type_name(p):
    '''type_name : specifier_qualifier_list
                 | specifier_qualifier_list abstract_declarator
    '''
    if(len(p) == 2):
      p[0] = p[1]
      p[0].name = 'TypeName'
      p[0].ast = build_AST(p)
    else:
      p[0] = Node(name = 'TypeName',val = '',type = p[1].type, lno = p[1].lno, children = [])
      p[0].ast = build_AST(p)

def p_abstract_declarator(p):
    '''abstract_declarator : pointer 
                           | direct_abstract_declarator
                           | pointer direct_abstract_declarator
    '''
    if(len(p) == 2):
      p[0] = p[1]
      p[0].name = 'AbstractDeclarator'
      p[0].ast = build_AST(p)
    elif(len(p) == 3):
      p[0] = Node(name = 'AbstractDeclarator',val = p[2].val,type = p[1].type + ' *', lno = p[1].lno, children = [])
      p[0].ast = build_AST(p)

def p_direct_abstract_declarator_1(p):
    '''direct_abstract_declarator : LPAREN abstract_declarator RPAREN
                                  | LSQUAREBRACKET RSQUAREBRACKET
                                  | LSQUAREBRACKET constant_expression RSQUAREBRACKET
                                  | direct_abstract_declarator LPAREN constant_expression RPAREN 
                                  | LPAREN RPAREN
                                  | LPAREN parameter_type_list RPAREN
                                  | direct_abstract_declarator LPAREN parameter_type_list RPAREN
    '''
    if(len(p) == 3):
      p[0] = Node(name = 'DirectAbstractDeclarator1',val = '',type = '', lno = p.lineno(1), children = [])
    elif(len(p) == 4):
      p[0] = p[2]
      p[0].name = 'DirectAbstractDeclarator1'
      p[0].ast = build_AST(p)
    else:
      p[0] = Node(name = 'DirectAbstractDeclarator1',val = p[1].val,type = p[1].val, lno = p[1].lno, children = [p[3]])
      p[0].ast = build_AST(p)

def p_direct_abstract_declarator_2(p):
  '''direct_abstract_declarator : direct_abstract_declarator LPAREN RPAREN'''
  p[0] = Node(name = 'DirectAbstractDEclarator2', val = p[1].val, type = p[1].type, lno = p[1].lno, children = [])
  p[0].ast = build_AST(p)

def p_initializer(p):
    '''initializer : assignment_expression
                   | openbrace initializer_list closebrace
                   | openbrace initializer_list COMMA closebrace
    '''
    if(len(p) == 2):
      p[0] = p[1]
      p[0].ast = build_AST(p)
    else:
      p[0] = p[2]
      p[0].name = 'Initializer'
    if(len(p) == 4):
      p[0].maxDepth = p[2].maxDepth + 1
      p[0].ast = build_AST(p)
    elif(len(p) == 5):
      p[0].ast = build_AST(p)

def p_initializer_list(p):
  '''initializer_list : initializer
  | initializer_list COMMA initializer
  '''
  if(len(p) == 2):
    p[0] = Node(name = 'InitializerList', val = '', type = '', children = [p[1]], lno = p.lineno(1), maxDepth = p[1].maxDepth)
    p[0].ast = build_AST(p)
  else:
    p[0] = Node(name = 'InitializerList', val = '', type = '', children = [], lno = p.lineno(1))
    p[0].ast = build_AST(p)
    if(p[1].name != 'InitializerList'):
      p[0].children.append(p[1])
    else:
      p[0].children = p[1].children
    p[0].children.append(p[3])
    p[0].maxDepth = max(p[1].maxDepth, p[3].maxDepth)

def p_statement(p):
    '''statement : labeled_statement
                 | compound_statement
                 | expression_statement
                 | selection_statement
                 | iteration_statement
                 | jump_statement
    '''
    p[0] = Node(name = 'Statement', val = '', type ='', children = [], lno = p.lineno(1))
    # print(p[1])
    if isinstance(p[1], Node):
      p[0].label = p[1].label
      p[0].expr = p[1].expr
    p[0].ast = build_AST(p)

def p_labeled_statement_1(p):
    '''labeled_statement : ID COLON statement '''
    p[0] = Node(name = 'LabeledStatement', val = '', type ='', children = [], lno = p.lineno(1) )
    p[0].ast = build_AST(p)

def p_labeled_statement_2(p):
    '''labeled_statement : SwMark1 CASE constant_expression COLON statement'''
    p[0] = Node(name = 'CaseStatement', val = '', type = '', children = [], lno = p.lineno(1))
    p[0].ast = build_AST(p,[1])
    p[0].expr.append(p[3].place)
    p[0].label.append(p[1])
    # print(p[0].label)

def p_labeled_statement_3(p):
    '''labeled_statement : SwMark1 DEFAULT COLON statement'''
    p[0] = Node(name = 'DefaultStatement', val = '', type = '', children = [], lno = p.lineno(1))
    p[0].ast = build_AST(p,[1])
    p[0].label.append(p[1])
    p[0].expr.append('')

def p_SwMark1(p):
  ''' SwMark1 : '''
  l = get_label()
  emit('label', '', '', l)
  p[0] = l

def p_compound_statement(p):
    '''compound_statement : openbrace closebrace
                          | openbrace statement_list closebrace
                          | openbrace declaration_list closebrace
                          | openbrace declaration_list statement_list closebrace
    '''  
    #TODO : see what to do in in first case
    if(len(p) == 3):
      p[0] = Node(name = 'CompoundStatement',val = '',type = '', lno = p.lineno(1), children = [])
    elif(len(p) == 4):
      p[0] = p[2]
      p[0].name = 'CompoundStatement'
      p[0].ast = build_AST(p)
    elif(len(p) == 4):
      p[0] = Node(name = 'CompoundStatement', val = '', type = '', children = [], lno = p.lineno(1))
      p[0].ast = build_AST(p)
    else:
      p[0] = Node(name = 'CompoundStatement', val = '', type = '', children = [], lno = p.lineno(1))
      p[0].ast = build_AST(p)

def p_function_compound_statement(p):
    '''function_compound_statement : LCURLYBRACKET closebrace
                          | LCURLYBRACKET statement_list closebrace
                          | LCURLYBRACKET declaration_list closebrace
                          | LCURLYBRACKET declaration_list statement_list closebrace
    '''  
    if(len(p) == 3):
      p[0] = Node(name = 'CompoundStatement',val = '',type = '', lno = p.lineno(1), children = [])
    elif(len(p) == 4):
      p[0] = p[2]
      p[0].name = 'CompoundStatement'
      p[0].ast = build_AST(p)
    elif(len(p) == 4):
      p[0] = Node(name = 'CompoundStatement', val = '', type = '', children = [], lno = p.lineno(1))
      p[0].ast = build_AST(p)
    else:
      p[0] = Node(name = 'CompoundStatement', val = '', type = '', children = [], lno = p.lineno(1))
      p[0].ast = build_AST(p)


def p_declaration_list(p):
    '''declaration_list : declaration
                        | declaration_list declaration
    '''
    if(len(p) == 2):
      p[0] = p[1]
      p[0].ast = build_AST(p)
    else:
      p[0] = Node(name = 'DeclarationList', val = '', type = '', children = [], lno = p.lineno(1))
      p[0].ast = build_AST(p)
      if(p[1].name != 'DeclarationList'):
        p[0].children.append(p[1])
      else:
        p[0].children = p[1].children
      p[0].children.append(p[2])

def p_statement_list(p):
    '''statement_list : statement
                      | statement_list statement
    '''
    if(len(p) == 2):
      p[0] = p[1]
      p[0].ast = build_AST(p)
    else:
      p[0] = Node(name = 'StatementList', val='', type='', children = [], lno = p.lineno(1))
      p[0].ast = build_AST(p)
      if(p[1].name != 'StatmentList'):
        p[0].children.append(p[1])
      else:
        p[0].children = p[1].children
      
      p[0].label = p[1].label
      p[0].expr = p[1].expr
      p[0].children.append(p[2])

def p_expression_statement(p):
    '''expression_statement : SEMICOLON
                            | expression SEMICOLON
    '''
    p[0] = Node(name = 'ExpressionStatement', val='', type='', children = [], lno = p.lineno(1))
    if(len(p) == 3):
      p[0].ast = build_AST(p)
      p[0].val = p[1].val
      p[0].type = p[1].type
      p[0].children = p[1].children
      p[0].place = p[1].place

    p[0].name = 'ExpressionStatement'
    # TODO : see what to do in case of only semicolon in rhs

def p_selection_statement_1(p):
    '''selection_statement : if LPAREN expression RPAREN IfMark1 statement %prec IFX'''
    p[0] = Node(name = 'IfStatment', val = '', type = '', children = [], lno = p.lineno(1))
    p[0].ast = build_AST(p, [5, 7])
    emit('label', '', '', p[5][0])
  
def p_selection_statement_2(p):
    '''selection_statement : if LPAREN expression RPAREN IfMark1 statement ELSE IfMark2 statement'''
    p[0] = Node(name = 'IfElseStatement', val = '', type = '', children = [], lno = p.lineno(1))
    p[0].ast = build_AST(p, [5, 8, 10])
    emit('label', '', '', p[5][1])

def p_IfMark1(p):
  '''IfMark1 : '''
  l1 = get_label()
  l2 = get_label()
  emit('ifgoto', p[-2].place, 'eq 0', l1)
  p[0] = [l1, l2]

def p_IfMark2(p):
  '''IfMark2 : '''
  emit('goto', '', '', p[-3][1])
  emit('label', '', '', p[-3][0])

def p_if(p):
  '''if : IF'''
  p[0] = p[1]
  p[0] = build_AST(p)

def p_selection_statement_3(p):
    '''selection_statement : switch LPAREN expression RPAREN SwMark2 statement SwMark3'''
    p[0] = Node(name = 'SwitchStatement', val = '', type = '', children = [], lno = p.lineno(1))
    global switchDepth
    switchDepth -= 1
    p[0].ast = build_AST(p,[5,7])
    if not (p[3].type == 'int' or p[3].type == 'short' or p[3].type == 'long' or p[3].type == 'char'):
      print("COMPILATION ERROR: Invalid data type used inside switch clause") 


def p_SwMark2(p):
  ''' SwMark2 : '''
  l1 = get_label()
  l2 = get_label()
  breakStack.append(l1)
  emit('goto','','',l2)
  p[0] = [l1, l2]


def p_SwMark3(p):
  ''' SwMark3 : '''
  emit('goto','','',p[-2][0])
  emit('label','','',p[-2][1])
  flag=0;
  lazy_label = ''
  for i in range(len(p[-1].label)):
    tmp_label = p[-1].label[i]
    tmp_exp = p[-1].expr[i]
    if tmp_exp == '':
      lazy_label = tmp_label
      flag=1
    else:
      emit('ifgoto', p[-4].place, 'eq ' + str(tmp_exp), tmp_label)
  if flag:
    emit('goto', '', '', lazy_label)
  emit('label','','',p[-2][0])
  breakStack.pop()


def p_switch(p):
  '''switch : SWITCH'''
  p[0] = p[1]
  global switchDepth
  switchDepth += 1
  p[0] = build_AST(p)

# remember : here statement added in grammar
def p_iteration_statement_1(p):
    '''iteration_statement : while WhMark1 LPAREN expression RPAREN WhMark2 statement WhMark3 '''
    p[0] = Node(name = 'WhileStatement', val = '', type = '', children = [], lno = p.lineno(1))
    global loopingDepth
    loopingDepth -= 1
    p[0] = build_AST(p,[2,6,8])
  
def p_while(p):
  '''while : WHILE'''
  global loopingDepth
  loopingDepth += 1
  p[0] = p[1]
  p[0] = build_AST(p)

def p_WhMark1(p):
  '''WhMark1 : '''
  l1 = get_label()
  l2 = get_label()
  continueStack.append(1)
  breakStack.append(2)
  emit('label', '', '', l1)
  p[0] = [l1 , l2]

def p_WhMark2(p):
  '''WhMark2 : '''
  emit('ifgoto', p[-2].place , 'eq 0', p[-4][1])

def p_WhMark3(p):
  '''WhMark3 : '''
  emit('goto','','',p[-6][0])
  emit('label','', '', p[-6][1])
  continueStack.pop()
  breakStack.pop()

def p_iteration_statement_2(p):
    '''iteration_statement : do DoM1 statement WHILE DoM2 LPAREN expression RPAREN DoM3 SEMICOLON'''
    p[0] = Node(name = 'DoWhileStatement', val = '', type = '', children = [], lno = p.lineno(1))
    global loopingDepth
    loopingDepth -= 1
    p[0].ast = build_AST(p,[2,5,9])

def p_do(p):
  '''do : DO'''
  global loopingDepth
  loopingDepth += 1
  p[0] = p[1]
  p[0] = build_AST(p)

def p_DoM1(p):
  '''DoM1 : '''
  l1 = get_label()
  l3 = get_label()
  continueStack.append(l1)
  breakStack.append(l3)
  emit('label', '', '', l1)
  p[0] = [l1 , l3]

def p_DoM3(p):
  '''DoM3 : '''
  emit('ifgoto', p[-2].place, 'eq 0', p[-7][1])
  emit('goto', '', '', p[-7][0])
  emit('label','','',p[-7][1])

def p_DoM2(p): 
  '''DoM2 : '''
  continueStack.pop()
  breakStack.pop()

def p_iteration_statement_3(p):
    '''iteration_statement : for LPAREN expression_statement forMark1 expression_statement forMark2 RPAREN statement forMark3'''
    p[0] = Node(name = 'ForWithoutStatement', val = '', type = '', children = [], lno = p.lineno(1))
    global loopingDepth
    loopingDepth -= 1
    p[0].ast = build_AST(p,[4,6,9])

def p_iteration_statement_4(p):
    '''iteration_statement : for LPAREN expression_statement forMark1 expression_statement forMark7 expression forMark4 RPAREN forMark5 statement forMark6'''
    p[0] = Node(name = 'ForWithStatement', val = '', type = '', children = [], lno = p.lineno(1)) 
    global loopingDepth
    loopingDepth -= 1
    p[0].ast = build_AST(p,[4,6,8,10,12])

def p_forMark1(p):
    '''forMark1 : '''
    l1 = get_label()
    l2 = get_label()
    l3 = get_label()
    l4 = get_label()
    continueStack.append(l1)
    breakStack.append(l2)
    emit('label', '', '', l1)
    p[0] = [l1, l2, l3, l4]

def p_forMark2(p):
    '''forMark2 : '''
    if p[-1].place:
      emit('ifgoto', p[-1].place, 'eq 0', p[-2][1])

def p_forMark7(p):
    '''forMark7 : '''
    if p[-1].place:
      emit('ifgoto', p[-1].place, 'eq 0', p[-2][1])
    emit('goto', '', '', p[-2][2])
    continueStack.pop()
    continueStack.append(p[-2][3])
    emit('label', '', '', p[-2][3])

def p_forMark3(p):
    '''forMark3 : '''
    emit('goto', '', '', p[-5][0])
    emit('label', '', '', p[-5][1])
    breakStack.pop()
    continueStack.pop()

def p_forMark4(p):
    '''forMark4 : '''
    emit('goto' , '', '', p[-4][0])

def p_forMark5(p):
    '''forMark5 : '''
    emit('label', '', '', p[-6][2])

def p_forMark6(p):
    '''forMark6 : '''
    emit('goto','','',p[-8][3])
    emit('label', '', '', p[-8][1])
    breakStack.pop()
    continueStack.pop()


def p_for(p):
  '''for : FOR'''
  global loopingDepth
  loopingDepth += 1
  p[0] = p[1]
  p[0] = build_AST(p)

def p_jump_statement(p):
    '''jump_statement : RETURN SEMICOLON
                      | RETURN expression SEMICOLON
    '''
    if(len(p) == 3):
      p[0] = Node(name = 'JumpStatement',val = '',type = '', lno = p.lineno(1), children = [])
      p[0].ast = build_AST(p)
      if(curFuncReturnType != 'void'):
        print('COMPILATION ERROR at line ' + str(p.lineno(1)) + ': function return type is not void')
      emit('ret', '', '', '')
    else:
      if(p[2].type in ['int','char','float'] and curFuncReturnType in ['int','char','float']):
        pass
      elif(p[2].type != '' and curFuncReturnType != p[2].type):
        print('warning at line ' + str(p.lineno(1)) + ': function return type is not ' + p[2].type)
      p[0] = Node(name = 'JumpStatement',val = '',type = '', lno = p.lineno(1), children = [])   
      p[0].ast = build_AST(p) 
      emit('ret', '', '', p[2].place)

def p_jump_statement_1(p):
  '''jump_statement : BREAK SEMICOLON'''
  global loopingDepth
  global switchDepth
  p[0] = Node(name = 'JumpStatement',val = '',type = '', lno = p.lineno(1), children = [])
  p[0].ast = build_AST(p)
  if(loopingDepth == 0 and switchDepth == 0):
    print(p[0].lno, 'break not inside loop')
  emit('goto','','',breakStack[-1])

def p_jump_statement_2(p):
  '''jump_statement : CONTINUE SEMICOLON'''
  global loopingDepth

  p[0] = Node(name = 'JumpStatement',val = '',type = '', lno = p.lineno(1), children = [])
  p[0].ast = build_AST(p)

  if(loopingDepth == 0):
    print(p[0].lno, 'continue not inside loop')

  emit('goto','','',continueStack[-1])

def p_jump_statement_3(p):
  '''jump_statement : GOTO ID SEMICOLON'''
  p[0] = Node(name = 'JumpStatement',val = '',type = '', lno = p.lineno(1), children = []) 
  p[0].ast = build_AST(p)   

def p_translation_unit(p):
    '''translation_unit : external_declaration
                        | translation_unit external_declaration
    '''
    p[0] = Node(name = 'JumpStatement',val = '',type = '', lno = p.lineno(1), children = [])
    if(len(p) == 2):
      p[0].children.append(p[1])
    else:
      p[0].children.append(p[2])
    p[0].ast = build_AST(p)
    
    

def p_external_declaration(p):
    '''external_declaration : function_definition
                            | declaration
    '''
    p[0] = p[1]
    p[0].name = 'ExternalDeclaration'
    p[0].ast = build_AST(p)

def p_function_definition_1(p):
    '''function_definition : declaration_specifiers declarator FuncMark1 declaration_list function_compound_statement                                                                            
    ''' 
    # removed from grammar
    # | declarator declaration_list function_compound_statement
    #                        | declarator function_compound_statement   
    #p[0] = Node()
    # p[0] = build_AST(p)  
    if(len(p) == 3):
      p[0] = Node(name = 'FuncDeclWithoutType',val = p[1].val,type = 'int', lno = p[1].lno, children = [])
    elif(len(p) == 4):
      p[0] = Node(name = 'FuncDeclWithoutType',val = p[1].val,type = 'int', lno = p[1].lno, children = [])
    else:
      # no need to keep type in AST
      p[0] = Node(name = 'FuncDecl',val = p[2].val,type = p[1].type, lno = p[1].lno, children = [])
      symbol_table[0][p[2].val]['isFunc'] = 1
    p[0].ast = build_AST(p)
    emit('funcEnd', '', '', p[2].val)


def p_function_definition_2(p):
  '''function_definition : declaration_specifiers declarator FuncMark1 function_compound_statement'''
  p[0] = Node(name = 'FuncDecl',val = p[2].val,type = p[1].type, lno = p.lineno(1), children = [])
  p[0].ast = build_AST(p)
  # print(p[2].val)
  symbol_table[0][p[2].val]['isFunc'] = 1
  emit('funcEnd', '', '', p[2].val)

def p_FuncMark1(p):
  '''FuncMark1 : '''
  emit('func', '', '', p[-1].val)

def p_openbrace(p):
  '''openbrace : LCURLYBRACKET'''
  global currentScope
  global nextScope
  parent[nextScope] = currentScope
  offset[nextScope] = 0
  currentScope = nextScope
  symbol_table.append({})
  nextScope = nextScope + 1
  scope_to_function[currentScope] = scope_to_function[parent[currentScope]]
  p[0] = p[1]

def p_lopenparen(p):
  '''lopenparen : LPAREN'''
  global currentScope
  global nextScope
  parent[nextScope] = currentScope
  offset[nextScope] = 0
  currentScope = nextScope
  symbol_table.append({})
  nextScope = nextScope + 1
  p[0] = p[1]

def p_closebrace(p):
  '''closebrace : RCURLYBRACKET'''
  global currentScope
  currentScope = parent[currentScope]
  p[0] = p[1]

# Error rule for syntax errors
def p_error(p):
    if(p):
      print("Syntax error in input at line " + str(p.lineno))

def runmain(code):
  open('graph1.dot','w').write("digraph G {")
  parser = yacc.yacc(start = 'translation_unit')
  pre_append_in_symbol_table()
  result = parser.parse(code,debug=False)
  print_emit_array(debug=True)
  open('graph1.dot','a').write("\n}")
  visualize_symbol_table()

  graphs = pydot.graph_from_dot_file('graph1.dot')
  # print(len(graphs))
  graph = graphs[0]
  graph.write_png('pydot_graph.png')

def print_emit_array(debug = False):
  global emit_array
  if (debug == False):
    return
  for i in emit_array:
    print(i)
def visualize_symbol_table():
  global scopeName
  with open("symbol_table_output.json", "w") as outfile:
    outfile.write('')
  for i in range (nextScope):
    if(len(symbol_table[i]) > 0 and i in scope_to_function.keys()):
      print('\nIn Scope ' + str(i))
      temp_list = {}
      for key in symbol_table[i].keys():
        # print(key, symbol_table[i][key])
        if(not key.startswith('struct')):
          temp_list[key] = symbol_table[i][key]
        if(not (key.startswith('struct') or key.startswith('typedef') or ('isFunc' in symbol_table[i][key].keys()) or key.startswith('__'))):
          newkey = key + "_" + str(i)
          global_symbol_table[key + "_" + str(i)] = symbol_table[i][key]
          # print(newkey, global_symbol_table[newkey])
          if(newkey not in local_vars[scope_to_function[i]]):
            local_vars[scope_to_function[i]].append(newkey)
          if i > 0:
            if key in func_arguments[scope_to_function[i]]:
              func_arguments[scope_to_function[i]].append(newkey)
              func_arguments[scope_to_function[i]].remove(key)
        elif key.startswith('__'):
          if(key not in strings.keys()):
            local_vars[scope_to_function[i]].append(key)
          global_symbol_table[key] = symbol_table[i][key]
          # print(key, global_symbol_table[key])
      json_object = json.dumps(temp_list, indent = 4)
      # print(json_object)
      with open("symbol_table_output.json", "a") as outfile:
        outfile.write('In \"' + scope_to_function[i] + "\"")
        outfile.write(json_object+"\n")
      print(local_vars)

