#!/usr/bin/env python3

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs

from test.helper import FakeYDL
from yt_dlp.extractor.creatsub import CreatsubChannelIE, CreatsubIE
from yt_dlp.utils import ExtractorError


class TestCreatsub(unittest.TestCase):
    POST_ID = '2e277678-224a-43ee-bca1-8905016b1beb'
    POST_URL = f'https://creatsub.io/post/{POST_ID}-sample'
    DESCRIPTION = f'# Sample post\n\n- {POST_URL}\n\nFirst & second.\nLast paragraph.'
    CHANNEL_URL = 'https://creatsub.io/creator'
    CHANNEL = '''
        <div class="modal"><h1>Login</h1></div>
        <h1><a href="/creator">Creator</a></h1>
        <div id="category">
            <a href="?categoryid=41"><strong class="text-primary">audiokniha</strong><br>67 posts</a>
            <a href="?categoryid=31"><strong class="text-primary">článek</strong><br>2 posts</a>
        </div>
    '''

    def _post(self, media=''):
        return f'''
            <meta property="og:url" content="{self.POST_URL}">
            <div class="card">
                <img src="/user-data/avatar.webp" class="rounded-circle">
                <a href="/creator" class="fw-bold">Creator</a>
                <img src="/post-data/{self.POST_ID}/cover.webp">
                <strong class="card-text-author">18.03.2025 11:06</strong>
                <div class="card-body">
                    <h1 class="card-title"><i class="bi bi-mic"></i>Sample post</h1>
                    <p class="card-text"><p><span class="ql-cursor">\ufeff\ufeff</span>First &amp; se\ufeffcond.</p><p>Last paragraph.</p>
                        <img src="/post-data/{self.POST_ID}/cover.webp">
                        <img src="https://images.example.com/inline.png"></p>
                </div>
                {media}
                <span class="totalCountLike-{self.POST_ID}">17</span>
            </div>
        '''

    def _card(self, index, locked=False):
        post_id = f'00000000-0000-0000-0000-{index:012d}'
        return f'''
            <div class="card mb-3">
                <h5 class="card-title">Post {index}</h5>
                {'<i class="bi bi-lock-fill"></i>' if locked else f'<a href="/post/{post_id}-sample">View post</a>'}
                <ul data-url="https://creatsub.io/post/{post_id}-sample"></ul>
            </div>
        '''

    def test_audio_and_metadata(self):
        ie = CreatsubIE(FakeYDL())
        webpage = self._post('<audio data-playlist-url="/file/audio?playlist=true"></audio>')
        with (
            patch.object(ie, '_download_webpage_handle', return_value=(webpage, SimpleNamespace(url=self.POST_URL))),
            patch.object(ie, '_extract_m3u8_formats_and_subtitles', return_value=(
                [{'url': 'https://creatsub.io/file/audio?playlist=true', 'ext': 'mp4'}], {})) as manifest,
        ):
            info = ie._real_extract(f'https://creatsub.io/post/{self.POST_ID}')
        self.assertEqual(info['id'], self.POST_ID)
        self.assertEqual(info['title'], 'Sample post')
        self.assertEqual(info['description'], self.DESCRIPTION)
        self.assertEqual(info['webpage_url'], self.POST_URL)
        self.assertEqual(info['channel'], 'Creator')
        self.assertEqual(info['upload_date'], '20250318')
        self.assertEqual(info['uploader_url'], self.CHANNEL_URL)
        self.assertEqual(info['uploader_id'], 'creator')
        self.assertEqual(info['like_count'], 17)
        self.assertEqual([t['url'] for t in info['thumbnails']], [
            f'https://creatsub.io/post-data/{self.POST_ID}/cover.webp',
            'https://images.example.com/inline.png',
        ])
        self.assertEqual(info['formats'][0]['vcodec'], 'none')
        self.assertEqual(info['formats'][0]['ext'], 'm4a')
        self.assertEqual(manifest.call_args.args[0], 'https://creatsub.io/file/audio?playlist=true')

    def test_multiple_media(self):
        ie = CreatsubIE(FakeYDL())
        webpage = self._post('''
            <video src="/file/video?playlist=true"></video>
            <audio controls><source src="/uploads/audio.mp3" type="audio/mpeg"></audio>
        ''')
        with (
            patch.object(ie, '_download_webpage_handle', return_value=(webpage, SimpleNamespace(url=self.POST_URL))),
            patch.object(ie, '_extract_m3u8_formats_and_subtitles', return_value=(
                [{'url': 'https://creatsub.io/file/video?playlist=true', 'ext': 'mp4'}],
                {'cs': [{'url': 'https://creatsub.io/captions.vtt'}]})),
        ):
            info = ie._real_extract(self.POST_URL)
        self.assertEqual(info['_type'], 'playlist')
        self.assertEqual([entry['id'] for entry in info['entries']], [f'{self.POST_ID}-1', f'{self.POST_ID}-2'])
        video, audio = info['entries']
        self.assertEqual(video['formats'][0]['ext'], 'mp4')
        self.assertNotEqual(video['formats'][0].get('vcodec'), 'none')
        self.assertIn('cs', video['subtitles'])
        self.assertEqual(audio['formats'][0]['url'], 'https://creatsub.io/uploads/audio.mp3')
        self.assertEqual(audio['formats'][0]['vcodec'], 'none')
        self.assertEqual(audio['description'], self.DESCRIPTION)
        self.assertEqual(audio['channel'], 'Creator')
        self.assertEqual(video['channel'], 'Creator')

    def test_youtube_embed(self):
        ie = CreatsubIE(FakeYDL())
        webpage = self._post('''
            <div id="youtubeInlinePlayer" data-youtube-url="https://www.youtube.com/watch?v=BaW_jenozKc"></div>
        ''')
        with patch.object(ie, '_download_webpage_handle', return_value=(webpage, SimpleNamespace(url=self.POST_URL))):
            info = ie._real_extract(self.POST_URL)
        self.assertEqual(info['_type'], 'url_transparent')
        self.assertEqual(info['ie_key'], 'Youtube')
        self.assertEqual(info['url'], 'https://www.youtube.com/watch?v=BaW_jenozKc')
        self.assertEqual(info['description'], self.DESCRIPTION)
        self.assertEqual(info['channel'], 'Creator')

    def test_locked_post(self):
        ie = CreatsubIE(FakeYDL({'ignore_no_formats_error': True}))
        with patch.object(ie, '_download_webpage_handle', return_value=(
            self.CHANNEL, SimpleNamespace(url=f'{self.CHANNEL_URL}?postId={self.POST_ID}'),
        )):
            with self.assertRaisesRegex(ExtractorError, 'This post is locked') as error:
                ie._real_extract(self.POST_URL)
        self.assertTrue(error.exception.expected)
        self.assertIn('--cookies-from-browser', str(error.exception))

    def test_text_and_image_post(self):
        with tempfile.TemporaryDirectory() as directory:
            ydl = FakeYDL({
                'ignore_no_formats_error': True,
                'skip_download': True,
                'writedescription': True,
                'outtmpl': f'{directory}/%(release_date>%Y-%m-%d.,upload_date>%Y-%m-%d.)s%(fulltitle,title)s.%(channel)s.[%(id)s].%(ext)s',
            })
            ydl.expect_warning('.*(no audio or video|No video formats found)')
            ie = CreatsubIE(ydl)
            with patch.object(ie, '_download_webpage_handle', return_value=(
                self._post(), SimpleNamespace(url=self.POST_URL),
            )):
                info = ie.extract(self.POST_URL)
            ydl.process_ie_result(info)
            self.assertEqual(
                Path(directory, f'2025-03-18.Sample post.Creator.[{self.POST_ID}].description').read_text(encoding='utf-8'),
                self.DESCRIPTION)
            self.assertEqual(len(info['thumbnails']), 2)
            self.assertEqual(info['formats'], [])

    def test_channel_pagination(self):
        ie = CreatsubChannelIE(FakeYDL())
        first_page = self.CHANNEL + ''.join(self._card(index, locked=True) for index in range(10))
        second_page = ''.join(self._card(index) for index in range(9, 19))
        with (
            patch.object(ie, '_download_webpage', return_value=first_page),
            patch.object(ie, '_download_json', side_effect=[{'html': second_page}, {'html': ''}]) as api,
            patch.object(ie, 'report_warning') as warning,
        ):
            result = ie._real_extract(self.CHANNEL_URL)
            entries = list(result['entries'])
        self.assertEqual(result['title'], 'Creator')
        self.assertEqual(result['channel'], 'Creator')
        self.assertEqual(len(entries), 9)
        self.assertEqual(warning.call_count, 10)
        self.assertTrue(all('Skipping locked post' in call.args[0] for call in warning.call_args_list))
        self.assertEqual([parse_qs(call.kwargs['data'].decode()) for call in api.call_args_list], [
            {'offset': ['10'], 'nick': ['creator']},
            {'offset': ['20'], 'nick': ['creator']},
        ])

    def test_categories(self):
        for suffix, category_id, name in (
            ('?categoryid=41', '41', 'audiokniha'),
            (':Audiokniha', '41', 'audiokniha'),
            (':%C4%8Cl%C3%A1nek', '31', 'článek'),
            ('/?other=value&categoryid=31', '31', 'článek'),
        ):
            with self.subTest(suffix=suffix):
                ie = CreatsubChannelIE(FakeYDL())
                with (
                    patch.object(ie, '_download_webpage', return_value=self.CHANNEL + self._card(99)),
                    patch.object(ie, '_download_json', return_value={
                        'html': self._card(1, locked=True) + self._card(2),
                    }) as api,
                    patch.object(ie, 'report_warning') as warning,
                ):
                    result = ie._real_extract(self.CHANNEL_URL + suffix)
                    entries = list(result['entries'])
                self.assertEqual(result['id'], f'creator-{category_id}')
                self.assertEqual(result['title'], f'Creator - {name}')
                self.assertEqual(result['channel'], 'Creator')
                self.assertEqual(len(entries), 1)
                self.assertEqual(entries[0]['id'], '00000000-0000-0000-0000-000000000002')
                warning.assert_called_once()
                api.assert_called_once()
                self.assertEqual(api.call_args.args[0], f'https://creatsub.io/post/category/posts/{category_id}')

    def test_unknown_category(self):
        for suffix in (':Missing', '?categoryid=999'):
            with self.subTest(suffix=suffix):
                ie = CreatsubChannelIE(FakeYDL())
                with patch.object(ie, '_download_webpage', return_value=self.CHANNEL):
                    with self.assertRaisesRegex(ExtractorError, 'Unknown category'):
                        ie._real_extract(self.CHANNEL_URL + suffix)

    def test_empty_category(self):
        ie = CreatsubChannelIE(FakeYDL())
        with (
            patch.object(ie, '_download_webpage', return_value=self.CHANNEL),
            patch.object(ie, '_download_json', return_value={'html': ''}) as api,
        ):
            result = ie._real_extract(self.CHANNEL_URL + ':Audiokniha')
            self.assertEqual(list(result['entries']), [])
        api.assert_called_once()


if __name__ == '__main__':
    unittest.main()
