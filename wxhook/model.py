from dataclasses import dataclass
from typing import Optional, Any, List, Dict

@dataclass
class Account:
    """用户"""
    account: str  # 账号名
    city: str  # 所在城市
    country: str  # 所在国家代码
    currentDataPath: str  # 当前数据路径，通常指向用户的WeChat文件夹
    dataSavePath: str  # 数据保存路径，通常指向用户的WeChat文件夹
    dbKey: str  # 数据库密钥，用于加密本地数据库
    headImage: str  # 头像图片URL
    mobile: str  # 手机号码
    name: str  # 昵称
    province: str  # 所在省份
    signature: str  # 用户个性签名
    wxid: str  # 微信ID


@dataclass
class Contact:
    """联系人"""
    customAccount: str  # 用户自定义的账号
    encryptName: str  # 加密名称，如果有的话
    nickname: str  # 用户的昵称
    pinyin: str  # 用户昵称的拼音首字母
    pinyinAll: str  # 用户昵称的完整拼音
    reserved1: int  # 预留字段1，具体用途未知
    reserved2: int  # 预留字段2，具体用途未知
    type: int  # 联系人类型
    verifyFlag: int  # 验证标志，用于表示用户的验证状态
    wxid: str  # 用户的微信ID


@dataclass
class ContactDetail:
    """联系人详情"""
    account: str  # 用户账号，如果未设置则为空字符串
    headImage: str  # 用户的头像图片URL，如果未设置则为空字符串
    nickname: str  # 用户昵称
    v3: str  # 用户的V3信息，通常用于加密或验证，可能包含特定的加密字符串
    wxid: str  # 用户的微信ID
    remark: str = ""  # 好友备注名，如果未设置则为空字符串


@dataclass
class Response:
    """API响应"""
    code: int
    msg: str
    data: Optional[Dict] = None

@dataclass
class Room:
    """群聊"""
    admin: str  # 管理员的用户ID，如果没有管理员则为空字符串
    chatRoomId: str  # 聊天室ID，如果没有指定聊天室则为空字符串
    notice: str  # 聊天室公告内容，如果没有设置公告则为空字符串
    xml: str  # 聊天室相关的XML信息，通常包含聊天室的详细配置信息，如果没有则为空字符串

@dataclass
class RoomMembers:
    """群成员"""
    admin: str  # 聊天室管理员的微信ID
    adminNickname: str  # 聊天室管理员的昵称
    chatRoomId: str  # 聊天室的ID
    memberNickname: str  # 正在提及的成员昵称，可能包含特殊字符作为昵称的一部分
    members: str  # 聊天室成员的微信ID列表，各ID之间使用特定字符分隔
    
@dataclass
class Table:
    """表结构"""
    name: str  # 任务名称
    rootpage: str  # 根页面
    sql: str  # SQL 创建表的语句
    tableName: str  # 表名称

@dataclass
class DB:
    """数据库"""
    databaseName: str  # 数据库名称
    handle: int  # 句柄
    tables: List[Table]  # 表列表


@dataclass
class Event:
    """消息事件"""
    content: Optional[Any] = None
    fromUser: Optional[str] = None
    toUser: Optional[str] = None
    type: Optional[int] = None