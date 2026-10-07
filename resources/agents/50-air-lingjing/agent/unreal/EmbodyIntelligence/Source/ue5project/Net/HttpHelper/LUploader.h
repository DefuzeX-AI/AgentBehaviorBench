#pragma once

#include "CoreMinimal.h"
#include "Interfaces/IHttpRequest.h"

class FLUploader;

struct FLUploadFileEntry
{
	FString FileField;
	FString FilePath;
	FString ContentType = TEXT("application/octet-stream");
};

struct FLUploadRawFileEntry
{
	FString FileField;
	FString FileName;
	TArray<uint8> FileData;
	FString ContentType = TEXT("application/octet-stream");
};

DECLARE_MULTICAST_DELEGATE_ThreeParams(FOnUploadComplete, const bool /*bSucceed*/, const FString& /*ResponseMessage*/, const TSharedPtr<FLUploader>& /*Uploader*/);

class UE5PROJECT_API FLUploader : public TSharedFromThis<FLUploader>
{
public:
	FLUploader() = default;
	~FLUploader() = default;

	void Upload(
		const FString& InUrl,
		const TArray<FLUploadFileEntry>& InFiles,
		const TMap<FString, FString>& InFields);

	void UploadRaw(
		const FString& InUrl,
		const TArray<FLUploadRawFileEntry>& InFiles,
		const TMap<FString, FString>& InFields);

	FOnUploadComplete& OnUploadComplete() { return UploadCompleteDelegate; }

private:
	static FString GenerateBoundary();
	static void BuildMultipartBody(
		const FString& InBoundary,
		const TMap<FString, FString>& InFields,
		const TArray<FLUploadRawFileEntry>& InFiles,
		TArray<uint8>& OutBody);

	void HandleRequestComplete(FHttpRequestPtr InRequest, FHttpResponsePtr InResponse, bool bConnectedSuccessfully);

	FOnUploadComplete UploadCompleteDelegate;
};
