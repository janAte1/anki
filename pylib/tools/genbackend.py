#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import re

from anki import backend_pb2 as pb
import stringcase

TYPE_DOUBLE = 1
TYPE_FLOAT = 2
TYPE_INT64 = 3
TYPE_UINT64 = 4
TYPE_INT32 = 5
TYPE_FIXED64 = 6
TYPE_FIXED32 = 7
TYPE_BOOL = 8
TYPE_STRING = 9
TYPE_GROUP = 10
TYPE_MESSAGE = 11
TYPE_BYTES = 12
TYPE_UINT32 = 13
TYPE_ENUM = 14
TYPE_SFIXED32 = 15
TYPE_SFIXED64 = 16
TYPE_SINT32 = 17
TYPE_SINT64 = 18

LABEL_OPTIONAL = 1
LABEL_REQUIRED = 2
LABEL_REPEATED = 3

# messages we don't want to unroll in codegen
SKIP_UNROLL_INPUT = {"TranslateString"}


def python_type(field):
    type = python_type_inner(field)
    if field.label == LABEL_REPEATED:
        type = f"Sequence[{type}]"
    return type


def python_type_inner(field):
    type = field.type
    if type == TYPE_BOOL:
        return "bool"
    elif type in (1, 2):
        return "float"
    elif type in (3, 4, 5, 6, 7, 13, 15, 16, 17, 18):
        return "int"
    elif type == TYPE_STRING:
        return "str"
    elif type == TYPE_BYTES:
        return "bytes"
    elif type == TYPE_MESSAGE:
        return fullname(field.message_type.full_name)
    elif type == TYPE_ENUM:
        return fullname(field.enum_type.full_name)
    else:
        raise Exception(f"unknown type: {type}")


def fullname(fullname):
    if "FluentString" in fullname:
        return fullname.replace("backend_proto", "anki.fluent_pb2")
    else:
        return fullname.replace("backend_proto", "pb")


# get_deck_i_d -> get_deck_id etc
def fix_snakecase(name):
    for fix in "a_v", "i_d":
        name = re.sub(
            f"(\w)({fix})(\w)",
            lambda m: m.group(1) + m.group(2).replace("_", "") + m.group(3),
            name,
        )
    return name


def get_input_args(msg):
    fields = sorted(msg.fields, key=lambda x: x.number)
    self_star = ["self"]
    if len(fields) >= 2:
        self_star.append("*")
    return ", ".join(self_star + [f"{f.name}: {python_type(f)}" for f in fields])


def get_input_assign(msg):
    fields = sorted(msg.fields, key=lambda x: x.number)
    return ", ".join(f"{f.name}={f.name}" for f in fields)


def render_method(method, idx):
    input_name = method.input_type.name
    if (
        (input_name.endswith("In") or len(method.input_type.fields) < 2)
        and not method.input_type.oneofs
        and not method.name in SKIP_UNROLL_INPUT
    ):
        input_args = get_input_args(method.input_type)
        input_assign = get_input_assign(method.input_type)
        input_assign_outer = (
            f"input = {fullname(method.input_type.full_name)}({input_assign})\n        "
        )
    else:
        input_args = f"self, input: {fullname(method.input_type.full_name)}"
        input_assign_outer = ""
    name = fix_snakecase(stringcase.snakecase(method.name))
    if len(method.output_type.fields) == 1:
        # unwrap single return arg
        f = method.output_type.fields[0]
        single_field = f".{f.name}"
        return_type = python_type(f)
    else:
        single_field = ""
        return_type = f"pb.{method.output_type.name}"
    return f"""\
    def {name}({input_args}) -> {return_type}:
        {input_assign_outer}output = pb.{method.output_type.name}()
        output.ParseFromString(self._run_command({idx+1}, input))
        return output{single_field}
"""


out = []
for idx, method in enumerate(pb._BACKENDSERVICE.methods):
    out.append(render_method(method, idx))

out = "\n".join(out)

path = "anki/rsbackend.py"

with open(path) as file:
    orig = file.read()

new = re.sub(
    "(?s)# @@AUTOGEN@@.*?# @@AUTOGEN@@\n",
    f"# @@AUTOGEN@@\n\n{out}\n    # @@AUTOGEN@@\n",
    orig,
)

with open(path, "wb") as file:
    file.write(new.encode("utf8"))
