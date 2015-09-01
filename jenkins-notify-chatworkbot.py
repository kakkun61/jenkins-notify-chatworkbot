#!/usr/bin/python
# -*- coding: utf-8 -*-
#

u'''
# Jenkins notify bot on chatwork
* Jenkins上でのビルド情報を監視して、コケてたら通知します
* 加えて、コケた状態から復活したら、それも通知します

# How to use
* config.jsonを書きます
    * config.examples以下のものを参考に作成します
* ```python jenkins-notify-chatworkbot.py &```を実行します
* 動きました。放置してください。お疲れ様です。
    * 初回起動時のみ全部通知しちゃいますが、許してください
'''

import datetime
import hashlib
import os
import random
import re
import time
import traceback
from xml.dom.minidom import parseString
from chatwork import *

################################################################################
###                          classes for general                             ###
################################################################################
class BuildStatus(object):
    u'''
    ビルド情報保持クラス.保存用
    '''
    def __init__(self, job_name, last_updated, last_status = ''):
        self.job_name = job_name
        self.last_updated = last_updated
        self.last_status = last_status

    def to_stored_line(self):
        u'''
        ローカルに保存する用のフォーマットで出力
        '''
        return self.job_name + ' ' + self.last_updated + ' ' + self.last_status

    @staticmethod
    def from_stored_line(line):
        u'''
        ローカルに保存してあるファイルの行のフォーマットでパースしつつBuildStatusオブジェクトを返却
        '''
        match = re.match(r'(\S*) (\S*) (\S*)', line, re.M | re.I)
        job_name = match.group(1)
        last_updated = match.group(2)
        last_status = match.group(3)
        return BuildStatus(job_name, last_updated, last_status)

    @staticmethod
    def from_jenkins_rss_latest(entry):
        u'''
        jenkinsのrssLatest APIから取得した時のフォーマット(XML)でパースしつつBuildStatusオブジェクトを返却
        '''
        title = entry.getElementsByTagName('title')[0].childNodes[0].data
        job_name = re.match(r'(\S*)', title, re.M | re.I).group(1)
        last_updated = entry.getElementsByTagName('updated')[0].childNodes[0].data
        return BuildStatus(job_name, last_updated)

class BuildInfo(object):
    u'''
    最新のビルド情報とかに使うクラス
    '''
    def __init__(self, full_display_name, job_url, is_building, status):
        self.full_display_name = full_display_name
        self.job_url = job_url
        self.is_building = is_building
        self.status = status

    @staticmethod
    def from_jenkins_job_last_build(xml):
        u'''
        jobs/hoge/lastBuildなAPIから取得した時のフォーマット(XML)でパースしつつBuildInfoオブジェクトを返却
        '''

        full_display_name = xml.getElementsByTagName('fullDisplayName')[0].childNodes[0].data
        building = xml.getElementsByTagName('building')[0].childNodes[0].data
        is_building = True if building == 'true' else False
        status = 'BUILDING' if is_building else xml.getElementsByTagName('result')[0].childNodes[0].data
        job_url = xml.getElementsByTagName('url')[0].childNodes[0].data
        return BuildInfo(full_display_name, job_url, is_building, status)

################################################################################
###                          classes for jenkins                             ###
################################################################################
class JenkinsClient(object):
    u'''
    JenkinsサーバーにアクセスするHTTPClientクラス
    '''
    def __init__(self, url):
        u'''

        :rtype : JenkinsClient
        '''
        self.url = url

    def rss_latest(self):
        u'''
        最新ビルドのrssを取得して、BuildStatusのリストで返却
        '''
        response = self.request('/rssLatest')
        xml = parseString(response)
        entries = xml.getElementsByTagName('entry')
        new_build_status = {}
        for entry in entries:
            status = BuildStatus.from_jenkins_rss_latest(entry)
            new_build_status[status.job_name] = status
        return new_build_status

    def job_last_build(self, job_name):
        u'''
        指定したjob_nameの最新ビルド情報を取得し、BuildInfoオブジェクトを返却
        '''
        response = self.request('/job/' + job_name + '/lastBuild/api/xml')
        xml = parseString(response)
        info = BuildInfo.from_jenkins_job_last_build(xml)
        return info

    def request(self, path):
        u'''
        Jenkinsの各種APIにアクセスし、レスポンスボディの文字列を返却
        '''
        conn = urllib2.urlopen(self.url + path + '?t=' + str(time.time()))
        response = conn.read()
        conn.close()
        return response

################################################################################
###                          implements for bot                              ###
################################################################################

class JenkinsNotifyPolicy(object):
    # ビルド成功可否
    BUILD = 1
    # ビルド失敗&ビルド成功
    BUILD_FIXED = 2
    # ビルド成功時のみ
    BUILD_SUCCESS = 4

    @staticmethod
    def from_str(value):
        if value == 'build': return JenkinsNotifyPolicy.BUILD
        if value == 'build_fixed': return JenkinsNotifyPolicy.BUILD_FIXED
        if value == 'build_success': return JenkinsNotifyPolicy.BUILD_SUCCESS
        return JenkinsNotifyPolicy.BUILD

class JenkinsNotifyReport(object):
    def __init__(self, job_name, full_display_name, policy, is_success, status, link):
        u'''
        :param job_name: job名
        :param full_display_name: job名とビルド番号を含む表示名
        :param policy: JenkinsNotifyPolicy
        :param is_success: ビルドが成功したか否か
        :param status: ビルドの詳細ステータス
        :param link: ビルド情報がみれるJenkinのURL
        :rtype : JenkinsNotifyReport
        '''
        self.job_name = job_name
        self.full_display_name = full_display_name
        self.policy = policy
        self.is_success = is_success
        self.status = status
        self.link = link

class JenkinsNotifyOption(object):
    default_policy = JenkinsNotifyPolicy.BUILD_FIXED
    default_message_prefix = 'Build'
    default_success_messages = ['Jenkins Build Report']
    default_failure_messages = ['Jenkins Build Report']
    default_success_emoticon = Emoticon.clap()
    default_failure_emoticon = Emoticon.devil()
    default_success_emoticon_str = 'clap'
    default_failure_emoticon_str = 'devil'
    def __init__(self,
            job_names,
            rooms = [],
            policy=default_policy,
            message_prefix=default_message_prefix,
            success_messages=default_success_messages,
            failure_messages=default_failure_messages,
            success_emoticon=default_success_emoticon,
            failure_emoticon=default_failure_emoticon):
        u'''
        :param job_names:
        :param rooms:
        :param policy:
        :param message_prefix:
        :param success_messages: 
        :param failure_messages: 
        :param success_emotion: 
        :param failure_emoticon: 
        :rtype : JenkinsNotifyOption
        '''
        self.job_names = job_names
        self.rooms = rooms
        self.policy = policy
        self.message_prefix = message_prefix
        self.success_messages = success_messages
        self.failure_messages = failure_messages
        self.success_emoticon = success_emoticon
        self.failure_emoticon = failure_emoticon

    @staticmethod
    def from_json(obj):
        jobs = obj['jobs']
        rooms = []
        for room_id in obj['rooms']: rooms.append(ChatworkRoom(room_id))
        policy = JenkinsNotifyPolicy.from_str(obj.get('policy', 'build_fixed'))
        message_prefix = obj.get('message_prefix', JenkinsNotifyOption.default_message_prefix)
        success_messages = obj.get('success_messages', JenkinsNotifyOption.default_success_messages)
        failure_messages = obj.get('failure_messages', JenkinsNotifyOption.default_failure_messages)
        success_emoticon = Emoticon(obj.get('success_emoticon', JenkinsNotifyOption.default_success_emoticon_str))
        failure_emoticon = Emoticon(obj.get('failure_emoticon', JenkinsNotifyOption.default_failure_emoticon_str))
        return JenkinsNotifyOption(
            jobs,
            rooms,
            policy,
            message_prefix,
            success_messages,
            failure_messages,
            success_emoticon,
            failure_emoticon
        )

class JenkinsNotifyConfig(object):
    u'''
    JenkinNotifyBotのConfiguration
    '''
    default_last_build_status_path = 'last_build_status.txt'
    default_interval = 120
    default_notify_options = []
    def __init__(self, checksum, api_token, jenkins_server_url, last_build_status_path, interval, notify_options):
        self.checksum = checksum
        self.api_token = api_token
        self.jenkins_server_url = jenkins_server_url
        self.last_build_status_path = last_build_status_path
        self.interval = interval
        self.notify_options = notify_options

    @staticmethod
    def from_file(path):
        u'''
        configファイルからJenkinsNotifyConfigオブジェクトを生成して返却
        '''
        last_build_status = {}
        lines = ''
        if os.path.exists(path):
            with open(path, 'r') as f: lines = f.readlines()
        conf_text = "".join(lines)
        checksum = hashlib.sha1(conf_text).hexdigest()
        conf_obj = json.loads(conf_text)
        api_token = ChatworkApiToken(conf_obj['api_token'])
        jenkins_server_url = conf_obj['jenkins_server_url']
        last_build_status_path = conf_obj.get('last_build_status_path', JenkinsNotifyConfig.default_last_build_status_path)
        interval = conf_obj.get('interval', JenkinsNotifyConfig.default_interval)
        options_json = conf_obj.get('notify_options', [])
        options = []
        for option_json in options_json:
            options.append(JenkinsNotifyOption.from_json(option_json))
        return JenkinsNotifyConfig(checksum, api_token, jenkins_server_url, last_build_status_path, interval, options)

    def is_same_config(self, that):
        return self.checksum == that.checksum

class JenkinsNotifyBot(object):
    def __init__(self, config_file_path = 'config.json'):
        u'''
        :param config:
        :rtype : JenkinsNotifyBot
        '''
        self._config_file_path = config_file_path
        self._chatwork = None
        self._jenkins = None
        self._config = None

    def run(self):
        self._update_config()
        while True:
            try:
                self._process()
            except Exception:
                print '%s %s' % (datetime.datetime.today().strftime('%x %X'), traceback.format_exc())
            self._sleep()
            try:
                self._update_config()
            except Exception:
                print '%s %s' % (datetime.datetime.today().strftime('%x %X'), traceback.format_exc())

    def _sleep(self):
        time.sleep(self._config.interval)

    def _update_config(self):
        new_config = JenkinsNotifyConfig.from_file(self._config_file_path)
        if (self._config is not None) and self._config.is_same_config(new_config): return
        self._config = new_config
        self._chatwork = ChatworkClient(self._config.api_token)
        self._jenkins = JenkinsClient(self._config.jenkins_server_url)
        print '%s Configuration has been updated.' % (datetime.datetime.today().strftime('%x %X'))

    def _process(self):
        u'''
        JenkinsNotifyBotのお仕事
        1. 最新ビルドが更新されてるかチェック
        2. されてたら最新情報を取得
        3. 最新ビルドがコケてたら通知
        4. コケてた状態から最新ビルドで復帰したら、通知
        5. デプロイ通知したいjobがあったら、最新ビルドが更新されてたら毎度通知
        '''
        last_build_status = self._read_last_build_status()
        new_build_status = self._jenkins.rss_latest()
        build_status_for_save = {}
        reports = []
        for job_name, build_status in new_build_status.iteritems():
            # new jobs!
            if not (job_name in last_build_status):
                last_build_status[job_name] = BuildStatus(job_name, 'new', 'FAILURE')

            # non-update
            if build_status.last_updated == last_build_status[job_name].last_updated:
                build_status_for_save[job_name] = last_build_status[job_name]
                continue

            # updated!
            build_info = self._jenkins.job_last_build(job_name)

            # continue if building now
            if build_info.is_building:
                build_status_for_save[job_name] = last_build_status[job_name]
                continue

            # detect build condition
            is_new_build_success, is_new_build_failure, is_build_fixed = self._detect_build_condition(last_build_status[job_name].last_status, build_info.status)
            print job_name, 'new_build_success:' + str(is_new_build_success), 'build_fixed:' + str(is_build_fixed)

            # report for build
            reports.append(
                JenkinsNotifyReport(
                    job_name,
                    build_info.full_display_name,
                    JenkinsNotifyPolicy.BUILD,
                    is_new_build_success,
                    build_info.status,
                    build_info.job_url
                )
            )

            # report for build_fixed
            is_notify_build = (is_new_build_failure or is_build_fixed)
            if is_notify_build:
                reports.append(
                    JenkinsNotifyReport(
                        job_name,
                        build_info.full_display_name,
                        JenkinsNotifyPolicy.BUILD_FIXED,
                        is_build_fixed,
                        build_info.status,
                        build_info.job_url
                    )
                )

            # report for build_success
            if is_new_build_success:
                reports.append(
                    JenkinsNotifyReport(
                        job_name,
                        build_info.full_display_name,
                        JenkinsNotifyPolicy.BUILD_SUCCESS,
                        is_new_build_success,
                        build_info.status,
                        build_info.job_url
                    )
                )

            # hold new status
            build_status.last_status = build_info.status
            build_status_for_save[job_name] = build_status

        self._notify_reports(reports, self._config.notify_options)
        self._write_last_build_status(build_status_for_save)

    def _detect_build_condition(self, last_status, new_status):
        is_new_build_success = (new_status == 'SUCCESS')
        is_new_build_failure = (new_status == 'FAILURE' or new_status == 'UNSTABLE')
        is_build_fixed = (
                (
                    last_status == 'FAILURE'
                    or last_status == 'UNSTABLE'
                )
                and new_status == 'SUCCESS'
        )
        return is_new_build_success, is_new_build_failure, is_build_fixed

    def _notify_reports(self, reports, options):
        u'''

        :param reports:
        :param options:
        '''
        for option in options:
            body = ''
            is_failure_once = False
            for report in reports:
                if report.policy != option.policy: continue
                if not (report.job_name in option.job_names): continue
                emoticon = option.success_emoticon if report.is_success else option.failure_emoticon
                if not is_failure_once: is_failure_once = not report.is_success
                body += self._build_message(report.full_display_name, emoticon, option.message_prefix, report.status, report.link)
            if body == '': continue
            title = ''
            if is_failure_once:
                random.shuffle(option.failure_messages)
                title = option.failure_messages[0]
            else:
                random.shuffle(option.success_messages)
                title = option.success_messages[0]
            message = self._decorate_message(title, body)
            for room in option.rooms:
                print room.id
                print message
                print '\n'
                self._chatwork.send_message(room, message)

    def _build_message(self, job_name, emoticon, prefix, status, url):
        u'''
        メッセージを生成
        '''
        return ChatworkMessageBuilder() \
            .with_body(' ') \
            .with_emoticon(emoticon) \
            .with_body(' ') \
            .with_body(job_name) \
            .with_body(': ') \
            .with_body(prefix) \
            .with_body(' ') \
            .with_body(status) \
            .with_body(' ') \
            .with_body(url) \
            .with_body('\n') \
            .build()

    def _decorate_message(self, title, report_body):
        u'''
        infoとかtitleでくくっておしゃれにしちゃう
        '''
        if not report_body: return ''
        if report_body[-1] == '\n': report_body = report_body[:-1]
        return ChatworkMessageBuilder() \
            .begin_info() \
                .begin_title() \
                    .with_body(title) \
                .end_title() \
                .with_body(report_body) \
            .end_info() \
            .build()

    def _read_last_build_status(self):
        u'''
        保存してあるビルド情報を取得
        '''
        last_build_status = {}
        lines = ''
        if os.path.exists(self._config.last_build_status_path):
            with open(self._config.last_build_status_path, 'r') as f: lines = f.readlines()
        for line in lines:
            status = BuildStatus.from_stored_line(line)
            last_build_status[status.job_name] = status
        return last_build_status

    def _write_last_build_status(self, build_status):
        u'''
        ビルド情報を保存
        '''
        text_to_write = ''
        for build_status in build_status.itervalues():
            text_to_write += build_status.to_stored_line()
            text_to_write += '\n'
        with open(self._config.last_build_status_path, 'w+') as f: f.write(text_to_write)

################################################################################
###                               entry point                                ###
################################################################################

def main():
    JenkinsNotifyBot().run()

if __name__ == '__main__':
    main()
