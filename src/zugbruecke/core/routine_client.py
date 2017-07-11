# -*- coding: utf-8 -*-

"""

ZUGBRUECKE
Calling routines in Windows DLLs from Python scripts running on unixlike systems
https://github.com/pleiszenburg/zugbruecke

	src/zugbruecke/core/routine_client.py: Classes for managing routines in DLLs

	Required to run on platform / side: [UNIX]

	Copyright (C) 2017 Sebastian M. Ernst <ernst@pleiszenburg.de>

<LICENSE_BLOCK>
The contents of this file are subject to the GNU Lesser General Public License
Version 2.1 ("LGPL" or "License"). You may not use this file except in
compliance with the License. You may obtain a copy of the License at
https://www.gnu.org/licenses/old-licenses/lgpl-2.1.txt
https://github.com/pleiszenburg/zugbruecke/blob/master/LICENSE

Software distributed under the License is distributed on an "AS IS" basis,
WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for the
specific language governing rights and limitations under the License.
</LICENSE_BLOCK>

"""


# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# IMPORT
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

import ctypes
from functools import partial
from pprint import pformat as pf

from .arg_definition import (
	pack_definition_argtypes,
	pack_definition_memsync,
	pack_definition_returntype
	)
from .const import (
	FLAG_POINTER,
	GROUP_VOID,
	GROUP_FUNDAMENTAL,
	GROUP_STRUCT
	)
from .memory import (
	overwrite_pointer_with_int_list,
	serialize_pointer_into_int_list
	)


# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
# DLL CLIENT CLASS
# +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

class routine_client_class():


	def __init__(self, parent_dll, routine_name):

		# Store handle on parent dll
		self.dll = parent_dll

		# Store pointer to zugbruecke session
		self.session = self.dll.session

		# For convenience ...
		self.client = self.dll.client

		# Get handle on log
		self.log = self.dll.log

		# Store my own name
		self.name = routine_name

		# Set call status
		self.called = False

		# Turn a bound method into a function ... HACK?
		self.handle_call = partial(self.__handle_call__)

		# By default, there is no memory to sync
		self.handle_call.memsync = []

		# By default, assume no arguments
		self.handle_call.argtypes = []

		# By default, assume c_int return value like ctypes expects
		self.handle_call.restype = ctypes.c_int

		# Tell server about routine
		self.__register_routine_on_server__()


	def __handle_call__(self, *args, **kw):
		"""
		TODO Optimize for speed!
		"""

		# Log status
		self.log.out('[routine-client] Trying to call routine "%s" in DLL file "%s" ...' % (self.name, self.dll.name))

		# Has this routine ever been called?
		if not self.called:

			# Log status
			self.log.out('[routine-client] ... has not been called before. Configuring ...')

			# Processing argument and return value types on first call TODO proper sanity check
			if hasattr(self.handle_call, 'memsync'):
				self.memsync = self.handle_call.memsync
			if hasattr(self.handle_call, 'argtypes'):
				self.argtypes = self.handle_call.argtypes
			if hasattr(self.handle_call, 'restype'):
				self.restype = self.handle_call.restype

			# Log status
			self.log.out('[routine-client]  memsync: %s' % pf(self.memsync))
			self.log.out('[routine-client]  argtypes: %s' % pf(self.argtypes))
			self.log.out('[routine-client]  restype: %s' % pf(self.restype))

			# Tell wine-python about types
			self.__push_argtype_and_restype__()

			# Change status of routine - it has been called once and is therefore configured
			self.called = True

			# Log status
			self.log.out('[routine-client] ... configured. Proceeding ...')

		# Log status
		self.log.out('[routine-client] ... parameters are %r / %r. Packing and pushing to server ...' % (args, kw))

		# Handle memory
		mem_package_list, memory_transport_handle = self.__pack_memory__(args)

		# Actually call routine in DLL! TODO Handle kw ...
		return_dict = self.client.call_dll_routine(
			self.dll.full_path, self.name, self.__pack_args__(self.argtypes_d, args), mem_package_list
			)

		# Log status
		self.log.out('[routine-client] ... received feedback from server, unpacking ...')

		# Unpack return dict (for pointers and structs)
		self.__unpack_return__(args, kw, return_dict)

		# Unpack memory
		self.__unpack_memory__(memory_transport_handle, return_dict['memory'])

		# Log status
		self.log.out('[routine-client] ... unpacked, return.')

		# Return result. return_value will be None if there was not a result.
		return return_dict['return_value']


	def __pack_args__(self, argtypes_p_sub, args): # TODO kw
		"""
		TODO Optimize for speed!
		"""

		# Shortcut for speed
		arguments_list = []

		# Step through arguments
		for arg_index, arg_definition_dict in enumerate(argtypes_p_sub):

			# Fetch current argument by index from tuple or by name from struct/kw
			if type(args) is list or type(args) is tuple:
				arg = args[arg_index]
			else:
				arg = getattr(args, arg_definition_dict['n'])

			# TODO:
			# append tuple to list "arguments_list"
			# tuple contains: (arg_definition_dict['n'], argument content / value)
			#  pointer: arg.value or arg.contents.value
			#  (value: Append value from ctypes datatype, because most of their Python equivalents are immutable)
			#  (contents.value: Append value from ctypes datatype pointer ...)
			#  by value: just "arg"

			try:

				arg_value = arg # Set up arg for iterative unpacking
				for flag in arg_definition_dict['f']: # step through flags

					# Handle pointers
					if flag == FLAG_POINTER:

						# There are two ways of getting the actual value
						if hasattr(arg_value, 'value'):
							arg_value = arg_value.value
						elif hasattr(arg_value, 'contents'):
							arg_value = arg_value.contents
						else:
							raise # TODO

					# Handle arrays
					elif flag > 0:

						arg_value = arg_value[:]

					# Handle unknown flags
					else:

						raise # TODO
			except:

				self.log.err(pf(arg_value))

			self.log.err('   abc')
			self.log.err(pf(arg_value))

			# Handle fundamental types
			if arg_definition_dict['g'] == GROUP_FUNDAMENTAL:

				# Append argument to list ...
				arguments_list.append((arg_definition_dict['n'], arg_value))

			# Handle structs
			elif arg_definition_dict['g'] == GROUP_STRUCT:

				# Reclusively call this routine for packing structs
				arguments_list.append((arg_definition_dict['n'], self.__pack_args__(
					arg_definition_dict['_fields_'], arg
					)))

			# Handle everything else ... likely pointers handled by memsync
			else:

				# Just return None - will (hopefully) be overwritten by memsync
				arguments_list.append(None)

		# Return parameter message list - MUST WORK WITH PICKLE
		return arguments_list


	def __pack_memory__(self, args):

		# Start empty package
		mem_package_list = []

		# Store pointers so they can eventually be overwritten
		memory_handle = []

		# Iterate over memory segments, which must be kept in sync
		for segment_index, segment in enumerate(self.memsync):

			# Reference args - search for pointer
			pointer = args
			# Step through path to pointer ...
			for path_element in segment['p']:
				# Go deeper ...
				pointer = pointer[path_element]

			# Reference args - search for length
			length = args
			# Step through path to pointer ...
			for path_element in segment['l']:
				# Go deeper ...
				length = length[path_element]

			# Defaut type, if nothing is given, is unsigned byte
			if '_t' not in segment.keys():
				segment['_t'] = ctypes.c_ubyte

			# Compute actual length - might come from ctypes or a Python datatype
			try:
				length_value = length.value * ctypes.sizeof(segment['_t'])
			except:
				length_value = length * ctypes.sizeof(segment['_t'])

			# Convert argument into ctypes datatype TODO more checks needed!
			if '_c' in segment.keys():
				arg_value = ctypes.pointer(segment['_c'].from_param(pointer))
			else:
				arg_value = pointer

			# Serialize the data ...
			data = serialize_pointer_into_int_list(arg_value, length_value)

			# Append data to package
			mem_package_list.append(data)

			# Append actual pointer to handler list
			memory_handle.append(arg_value)

		return mem_package_list, memory_handle


	def __process_memsync__(self, memsync, argtypes_p):

		# Start empty handle list
		memsync_handle = []

		# Iterate over memory segments, which must be kept in sync
		for segment in memsync:

			# Reference processed argument types - start with depth 0
			arg_type = argtypes_p[segment['p'][0]]
			# Step through path to argument type ...
			for path_element in segment['p'][1:]:
				# Go deeper ...
				arg_type = arg_type['_fields_'][path_element]

			# Reference processed argument types - start with depth 0
			len_type = argtypes_p[segment['l'][0]]
			# Step through path to argument type ...
			for path_element in segment['l'][1:]:
				# Go deeper ...
				len_type = len_type['_fields_'][path_element]

			# HACK make memory sync pointers type agnostic
			arg_type['g'] = GROUP_VOID
			arg_type['t'] = None # no type string

			# Add to list
			memsync_handle.append({
				'p': arg_type, # Handle on pointer argument definition
				'l': len_type # Handle on length argument definition
				})

		return memsync_handle


	def __push_argtype_and_restype__(self):

		# Prepare list of arguments by parsing them into list of dicts (TODO field name / kw)
		self.argtypes_d = pack_definition_argtypes(self.argtypes)

		# Parse return type
		self.restype_d = pack_definition_returntype(self.restype)

		# Reduce memsync
		self.memsync_d = pack_definition_memsync(self.memsync)
		self.memsync_handle = self.__process_memsync__(self.memsync, self.argtypes_d)

		# Pass argument and return value types as strings ...
		result = self.client.register_argtype_and_restype(
			self.dll.full_path, self.name, self.argtypes_d, self.restype_d, self.memsync_d
			)

		# Handle error
		if result == 0:
			raise # TODO


	def __register_routine_on_server__(self):

		# Log status
		self.log.out('[routine-client] Registering routine "%s" on server ...' % self.name)

		# Register routine in wine
		result = self.client.register_routine(self.dll.full_path, self.name)

		# If success ...
		if result:

			# Log status
			self.log.out('[routine-client] ... done (unconfigured).')

		# If failed ...
		else:

			# Log status
			self.log.out('[routine-client] ... failed!')

			raise # TODO


	def __unpack_memory__(self, pointer_list, memory_list):

		# Overwrite the local pointers with new data
		for pointer_index, pointer in enumerate(pointer_list):
			overwrite_pointer_with_int_list(pointer, memory_list[pointer_index])


	def __unpack_return__(self, args, kw, return_dict): # TODO kw not yet handled
		"""
		TODO Optimize for speed!
		"""

		# Get arguments' list
		arguments_list = return_dict['args']

		# Step through arguments
		for arg_index, arg in enumerate(args):

			# Fetch definition of current argument
			arg_definition_dict = self.argtypes_d[arg_index]

			# Handle fundamental types
			if arg_definition_dict['g'] == GROUP_FUNDAMENTAL:

				# Start process with plain old argument
				arg_value = args[arg_index]
				# New value is: arguments_list[arg_index]

				# Step through flags
				for flag in arg_definition_dict['f']:

					# Handle pointers
					if flag == FLAG_POINTER:

						# There are two ways of getting the actual value
						# if hasattr(arg_value, 'value'):
						# 	arg_value = arg_value.value
						if hasattr(arg_value, 'contents'):
							arg_value = arg_value.contents
						else:
							arg_value = arg_value

					# Handle arrays
					elif flag > 0:

						arg_value = arg_value

					# Handle unknown flags
					else:

						raise # TODO

				if hasattr(arg_value, 'value'):
					arg_value.value = arguments_list[arg_index]
				else:
					arg_value = arguments_list[arg_index]

				# # If by reference ...
				# if arg_definition_dict['p']:
				# 	# Put value back into its ctypes datatype
				# 	args[arg_index].value = arguments_list[arg_index]
				# # If by value
				# else:
				# 	# Nothing to do
				# 	pass

			# Handle everything else (structures and "the other stuff")
			else:

				# HACK TODO
				pass
