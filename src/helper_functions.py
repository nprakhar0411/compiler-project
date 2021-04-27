import pprint
from parser import emit_array, global_symbol_table, local_vars, func_arguments
instruction_array = []
leaders = [0]
nextuse = {}
live = {}
symbols = {}

class symbol_info:
    def __init__(self):
        self.address_desc_mem = []
        self.address_desc_reg = set()

class Instruction:
    def __init__(self,lno,quad):
        self.lno = lno
        self.src1 = None
        self.src2 = None
        self.dest = None
        self.jump_label = None
        self.op = None # instr_type
        self.instr_info = {}
        self.instr_info['nextuse'] = {}
        self.instr_info['live'] = {}
        self.argument_list = []
        self.fill_info(quad)

    def fill_info(self,quad):
        self.op = quad[0]
        if(self.op == "ifgoto"):
            self.dest = quad[3]
            self.src1 = quad[1]
            self.src2 = quad[2] # should change?

        elif(self.op == "goto"):
            self.dest = quad[3]

        elif(self.op == "inc" or self.op == "dec"):
            self.src1 = quad[3]

        elif(self.op == 'bitwisenot'):
            self.src1 = quad[3]

        elif(self.op == 'unot'):
            self.src1 = quad[3]

        elif(self.op == "param"):
            self.src1 = quad[3]

        elif(self.op == "ret"):
            if(quad[3] != ""):
                self.src1 = quad[3]

        elif(self.op == "func"):
            self.src1 = quad[3]

        elif(self.op == "call"):
            self.src1 = quad[3]
            self.src2 = quad[2]

        elif(self.op == "int_="):
            self.dest = quad[3]
            self.src1 = quad[1]
            if (quad[2] != ''):
                self.src2 = quad[2]

        elif(self.op == "label"):
            self.src1 = quad[3]

        elif(self.op == "int_uminus"):
            self.dest = quad[3]
            self.src1 = quad[1]

        elif(self.op.startswith("int_")):
            self.dest = quad[3]
            self.src1 = quad[1]
            self.src2 = quad[2]

        elif(self.op == "addr"):
            self.dest = quad[3]
            self.src1 = quad[1]

        elif(self.op == "*"):
            self.dest = quad[3]
            self.src1 = quad[1]

def find_basic_blocks():
    i = 1
    for quads in emit_array:
        instruction = Instruction(i,quads)
        instruction_array.append(instruction)
        op = quads[0] # assuming 0 is always instruction name
        extra = 0
        if(op in ["label","goto","ifgoto","ret","call","func","funcEnd"]):
            if(op != "label" and op != "func"):
                extra += 1
            leaders.append(i - 1 + extra)
        i += 1
    leaders.append(len(emit_array))
    # print(leaders)
    # print(instruction_array)

def is_symbol(var):
    if(var in global_symbol_table.keys()):
        return True
    else:
        return False

def is_number(number):
    number = str(number)
    if (number.startswith('-')):
        return True
    if number[0] == '.' or number[0].isnumeric():
        return True
    return False

def gen_next_use_and_live():
    for i in range(len(leaders) - 1):
        ignore_instr_list = ['param']
        block_start = leaders[i] + 1 # just the instruction next to the leader
        block_end = leaders[i + 1] - 1 # instruction previous to the next leader

        for j in range(block_start, block_end + 1): # doing forwards pass and filling default values
            cur_instr = instruction_array[j]
            src1, src2, dest = cur_instr.src1, cur_instr.src2, cur_instr.dest
            for operand in [src1, src2, dest]:
                if (operand != None and not operand.isnumeric()):
                    live[operand] = False
                    nextuse[operand] = None

        for j in range(block_end, block_start - 1, -1): # backward pass to set next use and live
            cur_instr = instruction_array[j]
            src1, src2, dest = cur_instr.src1, cur_instr.src2, cur_instr.dest
            if cur_instr.op in ignore_instr_list:
                continue
            if (dest != None and not dest.isnumeric() and is_symbol(dest)):
                if(dest not in symbols.keys()):
                    symbols[dest] = symbol_info()
                cur_instr.instr_info['live'][dest] = live[dest]
                cur_instr.instr_info['nextuse'][dest] = nextuse[dest]
                live[dest] = False
                nextuse[dest] = None
            if (src2 != None and not src2.isnumeric() and is_symbol(src2)):
                if(src2 not in symbols.keys()):
                    symbols[src2] = symbol_info()
                cur_instr.instr_info['live'][src2] = live[src2]
                cur_instr.instr_info['nextuse'][src2] = nextuse[src2]
                live[src2] = True
                nextuse[src2] = j
            if (src1 != None and not src1.isnumeric() and is_symbol(src1)):
                if(src1 not in symbols.keys()):
                    symbols[src1] = symbol_info()
                cur_instr.instr_info['live'][src1] = live[src1]
                cur_instr.instr_info['nextuse'][src1] = nextuse[src1]
                live[src1] = True
                nextuse[src1] = j
            # print("Instruction: " + str(emit_array[j]))
            pprint.pprint(cur_instr.instr_info)



def print_basic_blocks(debug = False):
    print("\n###### LEADERS ######")
    print(leaders)
    # print(instruction_array)
    for keys in symbols.keys():
        print(keys)
        
def runmain():
    find_basic_blocks()
    gen_next_use_and_live()
    # print_basic_blocks(debug = True)


