#pragma once

#include "CoreMinimal.h"
#include "LUploader.h"
#include "UObject/Object.h"
#include "LUploaderWrapper.generated.h"

USTRUCT(BlueprintType)
struct FLUploadFileEntryWrapper
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "HTTP|Uploader")
	FString FileField = TEXT("file");

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "HTTP|Uploader")
	FString FilePath;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "HTTP|Uploader")
	FString ContentType = TEXT("application/octet-stream");
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnUploadCompleteEvent, bool, bSucceed, const FString&, ResponseMessage);

UCLASS(BlueprintType, Blueprintable)
class UE5PROJECT_API ULUploaderWrapper : public UObject
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintCallable, Category = "HTTP|Uploader")
	void Upload(
		const FString& Url,
		const TArray<FLUploadFileEntryWrapper>& Files,
		const TMap<FString, FString>& Fields);

	UFUNCTION(BlueprintCallable, Category = "HTTP|Uploader")
	void UploadRaw(
		const FString& Url,
		const FString& FileField,
		const FString& FileName,
		const TArray<uint8>& FileData,
		const FString& ContentType,
		const TMap<FString, FString>& Fields);

	UPROPERTY(BlueprintAssignable, Category = "HTTP|Uploader")
	FOnUploadCompleteEvent OnUploadCompleteEvent;

private:
	void HandleUploadComplete(bool bSucceed, const FString& ResponseMessage, const TSharedPtr<FLUploader>& Uploader);

	TSharedPtr<FLUploader> UploaderPtr;
};
