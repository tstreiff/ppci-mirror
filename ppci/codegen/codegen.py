
"""
    Target independent code generator part. The target is provided when
    the generator is created.
"""

from .. import ir, irdag
from ..irutils import Verifier, split_block
from ..target import Target
from .registerallocator import RegisterAllocator
from ..binutils.outstream import MasterOutputStream, FunctionOutputStream
from ..binutils.outstream import TextOutputStream
import logging


class CodeGenerator:
    """ Generic code generator """
    def __init__(self, target):
        # TODO: schedule traces in better order.
        # This is optional!
        assert isinstance(target, Target), target
        self.logger = logging.getLogger('codegen')
        self.target = target
        self.dagger = irdag.Dagger()
        self.ins_sel = target.ins_sel
        self.register_allocator = RegisterAllocator()
        self.verifier = Verifier()

    def generate_function(self, irfunc, outs):
        """ Generate code for one function into a frame """
        self.logger.info('Generating {} code for {}'
                         .format(self.target, irfunc.name))
        instruction_list = []
        outs = MasterOutputStream([
            FunctionOutputStream(instruction_list.append),
            # TextOutputStream(),
            outs])

        # Create a frame for this function:
        frame = self.target.FrameClass(ir.label_name(irfunc))

        # Split too large basic blocks in smaller chunks (for literal pools):
        # TODO: fix arbitrary number of 500. This works for arm and thumb..
        for block in irfunc:
            while len(block) > 500:
                self.logger.debug('{} too large, splitting up'.format(block))
                _, block = split_block(block, pos=500)

        # Create selection dag (directed acyclic graph):
        dag = self.dagger.make_dag(irfunc, frame)
        self.logger.debug('DAG created')

        # Select instructions:
        self.ins_sel.munch_dag(dag, frame)
        self.logger.debug('Selected instructions')

        # Do register allocation:
        self.register_allocator.allocFrame(frame)
        self.logger.debug('Registers allocated, now adding final glue')
        # TODO: Peep-hole here?

        # Add label and return and stack adjustment:
        frame.EntryExitGlue3()

        # Materialize the register allocated instructions into a stream of
        # real instructions.
        self.target.lower_frame_to_stream(frame, outs)
        self.logger.debug('Instructions materialized')

    def generate(self, ircode, outs):
        """ Generate code into output stream """
        assert isinstance(ircode, ir.Module)

        # Generate code for global variables:
        outs.select_section('data')
        for global_variable in ircode.Variables:
            self.target.emit_global(outs, ir.label_name(global_variable))

        # Generate code for functions:
        # Munch program into a bunch of frames. One frame per function.
        # Each frame has a flat list of abstract instructions.
        outs.select_section('code')
        for function in ircode.Functions:
            self.generate_function(function, outs)
