#include "LUploader.h"

#include "HttpModule.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonSerializer.h"
#include "Dom/JsonObject.h"

void FLUploader::Upload(const FString& InUrl, const TArray<FLUploadFileEntry>& InFiles,
	const TMap<FString, FString>& InFields)
{
	TArray<FLUploadRawFileEntry> RawFiles;
	for (const auto& FileEntry : InFiles)
	{
		TArray<uint8> FileData;
		if (!FFileHelper::LoadFileToArray(FileData, *FileEntry.FilePath))
		{
			UE_LOG(LogTemp, Error, TEXT("LUploader: Failed to read file: %s"), *FileEntry.FilePath);
			continue;
		}

		FLUploadRawFileEntry RawEntry;
		RawEntry.FileField = FileEntry.FileField.IsEmpty() ? TEXT("file") : FileEntry.FileField;
		RawEntry.FileName = FPaths::GetCleanFilename(FileEntry.FilePath);
		RawEntry.FileData = MoveTemp(FileData);
		RawEntry.ContentType = FileEntry.ContentType;
		RawFiles.Add(MoveTemp(RawEntry));
	}

	UploadRaw(InUrl, RawFiles, InFields);
}

void FLUploader::UploadRaw(
	const FString& InUrl,
	const TArray<FLUploadRawFileEntry>& InFiles,
	const TMap<FString, FString>& InFields)
{
	TArray<FLUploadRawFileEntry> ValidFiles;
	for (const auto& File : InFiles)
	{
		if (File.FileData.Num() > 0)
		{
			ValidFiles.Add(File);
		}
	}

	if (ValidFiles.Num() == 0 && InFields.Num() == 0)
	{
		UE_LOG(LogTemp, Warning, TEXT("LUploader: No content to upload"));
		if (UploadCompleteDelegate.IsBound())
		{
			UploadCompleteDelegate.Broadcast(false, TEXT("LUploader: No content to upload"), AsShared());
		}
		return;
	}

	const FString Boundary = GenerateBoundary();

	TArray<uint8> BodyContent;
	BuildMultipartBody(Boundary, InFields, ValidFiles, BodyContent);

	FHttpModule::Get().SetHttpTimeout(600.0f);
	const TSharedPtr<IHttpRequest> Request = FHttpModule::Get().CreateRequest();
	Request->SetURL(InUrl);
	Request->SetVerb("POST");
	Request->SetTimeout(5000);
	Request->SetHeader(TEXT("Expect"), TEXT(""));
	Request->SetHeader(TEXT("Content-Type"), FString::Printf(TEXT("multipart/form-data; boundary=%s"), *Boundary));
	Request->SetContent(BodyContent);

	UE_LOG(LogTemp, Log, TEXT("LUploader: Sending request to %s with %d file(s)"), *InUrl, InFiles.Num());

	Request->OnProcessRequestComplete().BindRaw(this, &FLUploader::HandleRequestComplete);
	Request->ProcessRequest();
}

FString FLUploader::GenerateBoundary()
{
	const FString CharList = TEXT("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ");
	FString Boundary = TEXT("----HandsomeLaithLiu");
	for (int32 i = 0; i < 16; ++i)
	{
		Boundary += CharList[FMath::RandRange(0, CharList.Len() - 1)];
	}
	return Boundary;
}

void FLUploader::BuildMultipartBody(
	const FString& InBoundary,
	const TMap<FString, FString>& InFields,
	const TArray<FLUploadRawFileEntry>& InFiles,
	TArray<uint8>& OutBody)
{
	auto AppendString = [&OutBody](const FString& Str)
	{
		const FTCHARToUTF8 UTF8String(*Str);
		OutBody.Append(reinterpret_cast<const uint8*>(UTF8String.Get()), UTF8String.Length());
	};

	for (const auto& Pair : InFields)
	{
		AppendString(FString::Printf(TEXT("--%s\r\n"), *InBoundary));
		AppendString(FString::Printf(TEXT("Content-Disposition: form-data; name=\"%s\"\r\n\r\n"), *Pair.Key));
		AppendString(FString::Printf(TEXT("%s\r\n"), *Pair.Value));
	}

	for (const auto& File : InFiles)
	{
		AppendString(FString::Printf(TEXT("--%s\r\n"), *InBoundary));
		AppendString(FString::Printf(TEXT("Content-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"), *File.FileField, *File.FileName));
		AppendString(FString::Printf(TEXT("Content-Type: %s\r\n\r\n"), *File.ContentType));
		OutBody.Append(File.FileData);
		AppendString(TEXT("\r\n"));
	}

	AppendString(FString::Printf(TEXT("--%s--\r\n"), *InBoundary));
}

void FLUploader::HandleRequestComplete(FHttpRequestPtr InRequest, FHttpResponsePtr InResponse, bool bConnectedSuccessfully)
{
	bool bRealSuccess = false;
	FString Message;

	if (!InRequest.IsValid() || !bConnectedSuccessfully || !InResponse.IsValid())
	{
		Message = TEXT("LUploader: Network error or invalid response");
	}
	else
	{
		const int32 ResponseCode = InResponse->GetResponseCode();
		const FString ResponseContent = InResponse->GetContentAsString();

		if (EHttpResponseCodes::IsOk(ResponseCode))
		{
			bRealSuccess = true;
			Message = ResponseContent;
		}
		else
		{
			Message = FString::Printf(TEXT("LUploader: Server error (%d): %s"), ResponseCode, *ResponseContent);
		}
	}

	UE_LOG(LogTemp, Log, TEXT("LUploader: Request %s - %s"), bRealSuccess ? TEXT("succeeded") : TEXT("failed"), *Message);
	if (UploadCompleteDelegate.IsBound())
	{
		UploadCompleteDelegate.Broadcast(bRealSuccess, Message, AsShared());
	}
}
