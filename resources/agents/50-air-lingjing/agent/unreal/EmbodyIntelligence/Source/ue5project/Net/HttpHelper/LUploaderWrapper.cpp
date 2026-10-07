#include "LUploaderWrapper.h"
#include "LUploaderManager.h"

void ULUploaderWrapper::Upload(
	const FString& Url,
	const TArray<FLUploadFileEntryWrapper>& Files,
	const TMap<FString, FString>& Fields)
{
	TArray<FLUploadFileEntry> CoreFiles;
	for (const auto& WrapperEntry : Files)
	{
		FLUploadFileEntry Entry;
		Entry.FileField = WrapperEntry.FileField;
		Entry.FilePath = WrapperEntry.FilePath;
		Entry.ContentType = WrapperEntry.ContentType;
		CoreFiles.Add(MoveTemp(Entry));
	}

	UploaderPtr = FLUploaderManager::Get().CreateUploader();
	UploaderPtr->OnUploadComplete().AddUObject(this, &ULUploaderWrapper::HandleUploadComplete);
	UploaderPtr->Upload(Url, CoreFiles, Fields);
}

void ULUploaderWrapper::UploadRaw(
	const FString& Url,
	const FString& FileField,
	const FString& FileName,
	const TArray<uint8>& FileData,
	const FString& ContentType,
	const TMap<FString, FString>& Fields)
{
	FLUploadRawFileEntry RawEntry;
	RawEntry.FileField = FileField.IsEmpty() ? TEXT("file") : FileField;
	RawEntry.FileName = FileName;
	RawEntry.FileData = FileData;
	RawEntry.ContentType = ContentType;

	UploaderPtr = FLUploaderManager::Get().CreateUploader();
	UploaderPtr->OnUploadComplete().AddUObject(this, &ULUploaderWrapper::HandleUploadComplete);
	UploaderPtr->UploadRaw(Url, {RawEntry}, Fields);
}

void ULUploaderWrapper::HandleUploadComplete(bool bSucceed, const FString& ResponseMessage, const TSharedPtr<FLUploader>& Uploader)
{
	OnUploadCompleteEvent.Broadcast(bSucceed, ResponseMessage);
	UploaderPtr.Reset();
}
