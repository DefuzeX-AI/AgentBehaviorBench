#pragma once

#include "CoreMinimal.h"
#include "LUploader.h"

class UE5PROJECT_API FLUploaderManager
{
public:
	static FLUploaderManager& Get();

	TSharedPtr<FLUploader> CreateUploader();

private:
	FLUploaderManager() = default;
	~FLUploaderManager() = default;
	
	void OnUploadComplete(const bool bSucceed, const FString& InMessage, const TSharedPtr<FLUploader>& InUploader);
	
	TArray<TSharedRef<FLUploader>> ActiveUploaders;
};
