#pragma once

#include "CoreMinimal.h"
#include "LCapture.generated.h"

UCLASS()
class UE5PROJECT_API ULCaptureRenderTarget : public UObject
{
	GENERATED_BODY()

public:
	UPROPERTY()
	TObjectPtr<UTextureRenderTarget2D> RenderTarget;
};

class UE5PROJECT_API FLCapture : public TSharedFromThis<FLCapture>
{
public:
	static TSharedPtr<FLCapture> Create();

	void Capture(
		USceneCaptureComponent2D* CaptureComponent,
		int32 SizeX,
		int32 SizeY,
		const FString& SavePath,
		TFunction<void(const FString&)> OnComplete);

	~FLCapture();

private:
	void DoReadback() const;

	bool OnTick(float DeltaTime);
	TWeakObjectPtr<USceneCaptureComponent2D> SavedCaptureComponent;
	TWeakObjectPtr<UTextureRenderTarget2D> SavedOriginalTarget;

	TFunction<void(const FString&)> PendingCallback;
	FString PendingSavePath;
	int32 Width = 0;
	int32 Height = 0;
	bool bCapturing = false;
	int32 FrameCountdown = 0;
	FTSTicker::FDelegateHandle TickerHandle;
};
