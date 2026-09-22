from django.contrib import admin
from .models import PrescriptiveOutput, ChatbotLog, ProductClassification, ExternalVariable, KPIRecord, ArchiveStorage

admin.site.register(PrescriptiveOutput)
admin.site.register(ChatbotLog)
admin.site.register(ProductClassification)
admin.site.register(ExternalVariable)
admin.site.register(KPIRecord)
admin.site.register(ArchiveStorage)