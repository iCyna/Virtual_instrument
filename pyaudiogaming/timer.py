import pygame
class Timer:
	"""A simple timer class"""
	def __init__(self):
		self.restart()

	def restart(self):
		self.startTick=pygame.time.get_ticks()

	@property
	def elapsed(self):
		return pygame.time.get_ticks()-self.startTick