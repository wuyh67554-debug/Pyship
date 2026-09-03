# -*- coding: utf-8 -*-
"""opengl32.dll 最小绑定（GL 1.x/2.x 固定管线子集）。

仅供 Qt QOpenGLWidget 渲染器使用；所有函数必须在上下文 makeCurrent 后、
渲染线程内调用（Windows 下 opengl32 的当前上下文是线程局部的）。
"""

import ctypes
from ctypes import c_float, c_double, c_int, c_uint, c_ubyte, c_void_p, POINTER

_opengl32 = ctypes.windll.opengl32


def _gl(name, argtypes=None, restype=c_int):
    f = getattr(_opengl32, name)
    if argtypes is not None:
        f.argtypes = argtypes
    f.restype = restype
    return f


# ---------- 常量 ----------
GL_COLOR_BUFFER_BIT = 0x4000
GL_DEPTH_BUFFER_BIT = 0x0100
GL_POINTS = 0x0000
GL_LINES = 0x0001
GL_LINE_STRIP = 0x0003
GL_TRIANGLES = 0x0004
GL_TRIANGLE_STRIP = 0x0005
GL_QUADS = 0x0007

GL_DEPTH_TEST = 0x0B71
GL_CULL_FACE = 0x0B44
GL_BLEND = 0x0BE2
GL_LIGHTING = 0x0B50
GL_LIGHT0 = 0x4000
GL_LIGHT1 = 0x4001
GL_LIGHT2 = 0x4002
GL_LIGHT_MODEL_TWO_SIDE = 0x0B52
GL_LIGHT_MODEL_AMBIENT = 0x0B53
GL_COLOR_MATERIAL = 0x0B57
GL_NORMALIZE = 0x0BA1
GL_RESCALE_NORMAL = 0x803A
GL_LINE_SMOOTH = 0x0B20
GL_POLYGON_OFFSET_FILL = 0x8037
GL_POLYGON_OFFSET_LINE = 0x2A02
GL_PERSPECTIVE_CORRECTION_HINT = 0x0C50
GL_SRC_ALPHA = 0x0302
GL_ONE_MINUS_SRC_ALPHA = 0x0303
GL_CCW = 0x0901
GL_CW = 0x0900

GL_AMBIENT = 0x1200
GL_DIFFUSE = 0x1201
GL_SPECULAR = 0x1202
GL_EMISSION = 0x1600
GL_SHININESS = 0x1601
GL_AMBIENT_AND_DIFFUSE = 0x1602
GL_POSITION = 0x1203
GL_VERTEX_ARRAY = 0x8074
GL_NORMAL_ARRAY = 0x8075
GL_FLOAT = 0x1406

GL_SMOOTH = 0x1D01
GL_FLAT = 0x1D00
GL_FRONT = 0x0404
GL_BACK = 0x0405
GL_FRONT_AND_BACK = 0x0408
GL_FILL = 0x1B02
GL_LINE = 0x1B01
GL_POINT = 0x1B00
GL_PROJECTION = 0x1701
GL_MODELVIEW = 0x1700
GL_LEQUAL = 0x0203
GL_LESS = 0x0201
GL_ALWAYS = 0x0207
GL_REPLACE = 0x1E01
GL_NICEST = 0x1102
GL_FASTEST = 0x1101
GL_KEEP = 0x1E00

# ---------- 函数 ----------
clearColor = _gl('glClearColor', [c_float, c_float, c_float, c_float])
clear = _gl('glClear', [c_int])
viewport = _gl('glViewport', [c_int, c_int, c_int, c_int])
enable = _gl('glEnable', [c_int])
disable = _gl('glDisable', [c_int])
depthFunc = _gl('glDepthFunc', [c_int])
shadeModel = _gl('glShadeModel', [c_int])
polygonMode = _gl('glPolygonMode', [c_int, c_int])
lineWidth = _gl('glLineWidth', [c_float])
pointSize = _gl('glPointSize', [c_float])
matrixMode = _gl('glMatrixMode', [c_int])
loadIdentity = _gl('glLoadIdentity')
loadMatrixf = _gl('glLoadMatrixf', [POINTER(c_float)])
multMatrixf = _gl('glMultMatrixf', [POINTER(c_float)])
pushMatrix = _gl('glPushMatrix')
popMatrix = _gl('glPopMatrix')
ortho = _gl('glOrtho', [c_double] * 6)
frustum = _gl('glFrustum', [c_double] * 6)
translatef = _gl('glTranslatef', [c_float] * 3)
rotatef = _gl('glRotatef', [c_float] * 4)
scalef = _gl('glScalef', [c_float] * 3)
begin = _gl('glBegin', [c_int])
end = _gl('glEnd')
vertex3f = _gl('glVertex3f', [c_float] * 3)
vertex3fv = _gl('glVertex3fv', [POINTER(c_float)])
normal3f = _gl('glNormal3f', [c_float] * 3)
normal3fv = _gl('glNormal3fv', [POINTER(c_float)])
color3f = _gl('glColor3f', [c_float] * 3)
color4f = _gl('glColor4f', [c_float] * 4)
genLists = _gl('glGenLists', [c_int], c_uint)
newList = _gl('glNewList', [c_uint, c_int])
endList = _gl('glEndList')
callList = _gl('glCallList', [c_uint])
deleteLists = _gl('glDeleteLists', [c_uint, c_int])
lightfv = _gl('glLightfv', [c_int, c_int, POINTER(c_float)])
lightModelfv = _gl('glLightModelfv', [c_int, POINTER(c_float)])
materialfv = _gl('glMaterialfv', [c_int, c_int, POINTER(c_float)])
getFloatv = _gl('glGetFloatv', [c_int, POINTER(c_float)])
getIntegerv = _gl('glGetIntegerv', [c_int, POINTER(c_int)])
getError = _gl('glGetError')
getString = _gl('glGetString', [c_int], c_void_p)
blendFunc = _gl('glBlendFunc', [c_int, c_int])
frontFace = _gl('glFrontFace', [c_int])
cullFace = _gl('glCullFace', [c_int])
depthMask = _gl('glDepthMask', [c_ubyte])
polygonOffset = _gl('glPolygonOffset', [c_float, c_float])
hint = _gl('glHint', [c_int, c_int])
flush = _gl('glFlush')
finish = _gl('glFinish')
enableClientState = _gl('glEnableClientState', [c_int])
disableClientState = _gl('glDisableClientState', [c_int])
vertexPointer = _gl('glVertexPointer', [c_int, c_int, c_int, c_void_p])
normalPointer = _gl('glNormalPointer', [c_int, c_int, c_void_p])
drawArrays = _gl('glDrawArrays', [c_int, c_int, c_int])
pointSize = _gl('glPointSize', [c_float])

GL_COMPILE = 0x1300


def farr(a):
    """Python 序列 -> ctypes float 数组"""
    return (c_float * len(a))(*[float(x) for x in a])


def string_val(ptr):
    if not ptr:
        return ''
    return ctypes.string_at(ptr).decode(errors='replace')


def err_str():
    e = getError()
    m = {0: 'GL_NO_ERROR', 0x0500: 'GL_INVALID_ENUM', 0x0501: 'GL_INVALID_VALUE',
         0x0502: 'GL_INVALID_OPERATION', 0x0503: 'GL_STACK_OVERFLOW',
         0x0504: 'GL_STACK_UNDERFLOW', 0x0505: 'GL_OUT_OF_MEMORY'}
    return m.get(e, '0x%04X' % e)
