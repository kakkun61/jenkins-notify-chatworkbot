# -*- coding: utf-8 -*-

import urllib
import urllib2
import json

class Identity(object):
    u'''
    識別子
    '''
    def __init__(self, value):
        self.value = value
    def __eq__(self, other):
        return self.value == other.value
    def __ne__(self, other):
        return self.value != other.value

################################################################################
###                          classes for chatwork                            ###
################################################################################

class ChatworkApiToken(object):
    u'''
    '''
    def __init__(self, value):
        u'''
        :param value:
        :rtype : ChatworkApiToken
        '''
        self.value = value

class ChatworkRoom(object):
    u'''
    chatworkの部屋
    id: 部屋のID
    '''
    def __init__(self, roomId):
        u'''
        :param roomId:
        :rtype : ChatworkRoom
        '''
        self.id = roomId

class ChatworkMessageId(Identity):
    def __init__(self, value):
        Identity.__init__(self, value)

    @staticmethod
    def from_json(obj):
        r = ChatworkMessageId(obj['message_id'])
        return r

class Emoticon(object):
    u'''
    エモーティコン
    '''
    def __init__(self, value):
        u'''
        :param value:
        :rtype : Emoticon
        '''
        self.value = '(' + value + ')'

    @staticmethod
    def devil():
        u'''
        黒いやつ
        :rtype : Emoticon
        '''
        return Emoticon('devil')

    @staticmethod
    def clap():
        u'''
        拍手してるやつ
        :rtype : Emoticon
        '''
        return Emoticon('clap')

    @staticmethod
    def flex():
        u'''
        筋肉モリモリなやつ
        :rtype : Emoticon
        '''
        return Emoticon('flex')

    @staticmethod
    def puke():
        u'''
        ウゲーってやつ
        :rtype : Emoticon
        '''
        return Emoticon('puke')

    @staticmethod
    def roger():
        u'''
        了解！なやつ。ラジャー
        :rtype : Emoticon
        '''
        return Emoticon('roger')

class ChatworkMessageBuilder(object):
    u'''
    chatworkのchat文字列を生成するimmutable Builderクラス
    '''
    def __init__(self, ctx = None):
        u'''
        :param ctx:
        :rtype : object
        '''
        if ctx is None:
            self._info_writing = False
            self._title_writing = False
            self._text = ''
            return
        self._info_writing = ctx._info_writing
        self._title_writing = ctx._title_writing
        self._text = ctx._text

    def begin_info(self):
        u'''
        infoを開始
        '''
        if self._info_writing: raise Exception('info was started')
        r = ChatworkMessageBuilder(self)
        r._text += '[info]'
        r._info_writing = True
        return r

    def end_info(self):
        u'''
        infoを終了
        '''
        if not self._info_writing: raise Exception('info was not started.')
        r = ChatworkMessageBuilder(self)
        r._text += '[/info]'
        r._info_writing = False
        return r

    def begin_title(self):
        u'''
        titleを開始
        '''
        if self._title_writing: raise Exception('title was started')
        r = ChatworkMessageBuilder(self)
        r._text += '[title]'
        r._title_writing = True
        return r

    def end_title(self):
        u'''
        titleを終了
        '''
        if not self._info_writing: raise Exception('title was not started.')
        r = ChatworkMessageBuilder(self)
        r._text += '[/title]'
        r._title_writing = False
        return r

    def with_body(self, text):
        u'''
        chat文字列に指定したtextを含める
        '''
        r = ChatworkMessageBuilder(self)
        r._text += text
        return r

    def with_emoticon(self, emoticon):
        u'''
        chat文字列に指定したEmoticonを含める
        '''
        r = ChatworkMessageBuilder(self)
        r._text += emoticon.value
        return r

    def is_valid(self):
        u'''
        ビルド可能な状態か否かを返却
        '''
        if not (not self._info_writing and not self._title_writing): return False
        return True

    def build(self):
        u'''
        ビルドを実施し、chat用の文字列を返却
        '''
        if not self.is_valid(): raise Exception('Are you finished writing title or info?')
        return self._text

class ChatworkClient(object):
    def __init__(self, token, base_url = 'https://api.chatwork.com/v1/'):
        u'''
        :param token: ChatworkApiToken
        :rtype : ChatworkClient
        '''
        self.token = token
        self.base_url = base_url

    def send_message(self, room, message):
        u'''
        :param room: ChatworkRoom
        :param message: text
        '''
        url = self.base_url + 'rooms/' + room.id + '/messages'
        req = self._create_request(url)
        params = urllib.urlencode({'body': message.encode('utf-8')})
        response = urllib2.urlopen(req, params)
        raw_body = response.read()
        json_obj = json.loads(raw_body)
        return ChatworkMessageId.from_json(json_obj)

    def _create_request(self, url):
        req = urllib2.Request(url)
        req.add_header('X-ChatWorkToken', self.token.value)
        return req
