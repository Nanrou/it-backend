"""
权限配置
"""


class Permission:
    """
    WRITE:                写
    HIGHER:               高级，可以跨部门
    MAINTENANCE:          维修
    MAINTENANCE_HIGHER:   维修高级
    SUPER:                普通管理员
    SUPREME:              超级管理员
    """
    WRITE = 0b000001
    HIGHER = 0b000010
    MAINTENANCE = 0b000100
    MAINTENANCE_HIGHER = 0b001000
    SUPER = 0b010000
    SUPREME = 0b100000

