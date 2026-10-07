#include "LUploaderManager.h"

FLUploaderManager& FLUploaderManager::Get()
{
	static FLUploaderManager Instance;
	return Instance;
}

TSharedPtr<FLUploader> FLUploaderManager::CreateUploader()
{
	TSharedRef<FLUploader> Uploader = MakeShared<FLUploader>();
	Uploader->OnUploadComplete().AddRaw(this, &FLUploaderManager::OnUploadComplete);
	ActiveUploaders.Add(Uploader);
	return Uploader;
}

void FLUploaderManager::OnUploadComplete(const bool bSucceed, const FString& InMessage,
	const TSharedPtr<FLUploader>& InUploader)
{
	if (InUploader.IsValid())
	{
		ActiveUploaders.Remove(InUploader.ToSharedRef());
	}
}

