from django.db import models
from django.contrib.auth.models import User
import swiftclient
from datetime import datetime
from django.conf import settings
from .utils import temp_generator

USERNAME = settings.SW_USERNAME
KEY = settings.SW_KEY
AUTH_URL = settings.SW_AUTH_URL

USER_MODEL = settings.AUTH_USER_MODEL
DEFAULT_CONTAINER_TITLE = 'Main_container'

class SwiftContainer(models.Model):
	title = models.CharField(max_length=255, default = DEFAULT_CONTAINER_TITLE)
	service_slug = models.CharField('service slug', max_length=30, unique=True, blank=False, default = USERNAME)
	date_created = models.DateTimeField(auto_now_add=True)

	class Meta:
		db_table = 'sw_container'
		ordering = ['-date_created']
		verbose_name = 'sw_container'
		verbose_name_plural = 'sw_containers'

	def __unicode__(self):
		return self.title

	@classmethod 
	def create_default_container(cls):
		try:
			container = cls(title=DEFAULT_CONTAINER_TITLE, service_slug=USERNAME)
			conn = swiftclient.Connection(user=USERNAME, key=KEY, authurl=AUTH_URL)
			conn.put_container(container.title)
			container.save()
		except swiftclient.ClientException:
			raise Exception("Access denied")

		return container

	@classmethod 
	def create_container(cls, title):
		try:
			container = cls(title=title, service_slug=USERNAME)
			conn = swiftclient.Connection(user=USERNAME, key=KEY, authurl=AUTH_URL)
			conn.put_container(container.title)
			container.save()
		except swiftclient.ClientException:
			raise Exception("Access denied")

		return container

	def delete(self, **kwargs):
		try:
			conn = swiftclient.Connection(user=USERNAME, key=KEY, authurl=AUTH_URL)
			_m, objects = conn.get_container(self.title)
			for obj in objects:
				conn.delete_object(self.title, obj['name'])
			conn.delete_container(self.title)
		except swiftclient.ClientException:
			raise Exception("Access denied")
		super(self.__class__, self).delete(**kwargs)


class SwiftFile(models.Model):
	date_created = models.DateTimeField(auto_now_add=True)
	filename = models.CharField(max_length=255)
	author = models.ForeignKey(USER_MODEL, verbose_name='user', related_name='files_set', blank=True, null=True)
	filesize = models.IntegerField(blank=True, null=True)
	content_type = models.CharField(max_length=100)
	container = models.ForeignKey('SwiftContainer', related_name='files')
	date_modified = models.DateTimeField(auto_now=True, default=datetime.now())
	temp_url = models.CharField(max_length=255)
	key = models.CharField(max_length=40)

	class Meta:
		db_table = 'sw_file'
		ordering = ['-date_created']
		verbose_name = 'sw_file'
		verbose_name_plural = 'sw_files'

	def __unicode__(self):
		return self.filename 

	@property
	def url(self):
		if (self.date_modified.replace(tzinfo=None) - datetime.now()).days > 5:
			self.temp_url = get_temp_download_url()
			self.save()
		return self.temp_url

	@classmethod
	def upload_file(cls, file_contents, filename, content_type,  author=None):
		f = cls(author=author)
		f.filename=filename
		f.content_type=content_type
		f.key = f.generate_key()
		try:
			container = SwiftContainer.objects.get(title=DEFAULT_CONTAINER_TITLE, service_slug=USERNAME)
		except SwiftContainer.DoesNotExist:
			container = SwiftContainer.create_default_container()
		try:
			conn = swiftclient.Connection(user=USERNAME, key=KEY, authurl=AUTH_URL)
			conn.put_object(container.title, f.key, contents=file_contents, content_type=content_type)
		except swiftclient.ClientException:
			raise Exception("Access denied")
		f.container = container
		f.save()
		return f

	@classmethod
	def search_files(cls, filename):
		return cls.objects.filter(filename__startswith=filename)


	def get_temp_download_url(self):
		try:
			conn = swiftclient.Connection(user=USERNAME, 
											key=KEY, authurl=AUTH_URL)
			url = temp_generator.get_temp_url(connection = conn, filename=self.key, container=self.container.title, expires=7 * 24 * 3600)
		except swiftclient.ClientException:
			raise Exception("Access denied")
		return url

	def delete(self, **kwargs):
		try:
			conn = swiftclient.Connection(user=USERNAME, 
											key=KEY, authurl=AUTH_URL)
			conn.delete_object(self.container.title, self.key)
		except swiftclient.ClientException:
			raise Exception("Access denied")
		super(self.__class__, self).delete(**kwargs)

	def generate_key(self):
		import hashlib, random
		salt = hashlib.sha1(str(random.random())).hexdigest()[:5]
		filename = str(self.filename)
		if isinstance(filename, unicode):
			filename = filename.encode('utf-8')
		content_type = str(self.content_type)
		if isinstance(content_type, unicode):
			content_type = content_type.encode('utf-8')
		key = hashlib.sha1(salt+filename+content_type).hexdigest()
		try:
			splited_filename = filename.split(".")
			if len(splited_filename) > 1:
				type_suffix = splited_filename[-1]
			else:
				type_suffix = ""
		except Exception:
			type_suffix = ""
		finally:
			if len(type_suffix) != 0:
				key = key + "." + type_suffix
		return key

	def save(self, **kwargs):
		self.temp_url = self.get_temp_download_url()
		if not self.key:
			self.key = self.generate_key()
		super(self.__class__, self).save(**kwargs)


