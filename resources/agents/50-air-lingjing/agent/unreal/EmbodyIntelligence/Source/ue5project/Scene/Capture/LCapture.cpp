#include "LCapture.h"
#include "Components/SceneCaptureComponent2D.h"
#include "Engine/TextureRenderTarget2D.h"
#include "IImageWrapper.h"
#include "IImageWrapperModule.h"
#include "Modules/ModuleManager.h"
#include "Misc/FileHelper.h"

TSharedPtr<FLCapture> FLCapture::Create()
{
	return MakeShared<FLCapture>();
}

FLCapture::~FLCapture()
{
	if (TickerHandle.IsValid())
	{
		FTSTicker::GetCoreTicker().RemoveTicker(TickerHandle);
		TickerHandle.Reset();
	}

	if (SavedCaptureComponent.Get() && SavedOriginalTarget.Get())
	{
		SavedCaptureComponent->TextureTarget = SavedOriginalTarget.Get();
	}
}

void FLCapture::Capture(
	USceneCaptureComponent2D* CaptureComponent,
	const int32 SizeX,
	const int32 SizeY,
	const FString& SavePath,
	TFunction<void(const FString&)> OnComplete)
{
	if (!CaptureComponent)
	{
		UE_LOG(LogTemp, Error, TEXT("LCapture: CaptureComponent is null"));
		if (OnComplete)
		{
			OnComplete(SavePath);
		}
		return;
	}

	if (bCapturing)
	{
		UE_LOG(LogTemp, Warning, TEXT("LCapture: Already capturing"));
		return;
	}

	Width = FMath::Max(1, SizeX);
	Height = FMath::Max(1, SizeY);

	// Swap render target
	SavedCaptureComponent = CaptureComponent;
	SavedOriginalTarget = CaptureComponent->TextureTarget;
	SavedOriginalTarget->InitCustomFormat(Width, Height, PF_B8G8R8A8, false);

	CaptureComponent->CaptureSource = SCS_FinalColorLDR;
	CaptureComponent->CaptureSceneDeferred();

	PendingCallback = MoveTemp(OnComplete);
	PendingSavePath = SavePath;
	bCapturing = true;
	FrameCountdown = 2;

	// Keep this instance alive during the async capture
	TSharedPtr<FLCapture> Self = AsShared();

	TickerHandle = FTSTicker::GetCoreTicker().AddTicker(
		FTickerDelegate::CreateLambda([Self](float DeltaTime) -> bool
		{
			return Self->OnTick(DeltaTime);
		}), 0.0f);
}

bool FLCapture::OnTick(float DeltaTime)
{
	if (!bCapturing)
	{
		return false;
	}

	--FrameCountdown;
	if (FrameCountdown > 0)
	{
		return true;
	}

	if (TickerHandle.IsValid())
	{
		FTSTicker::GetCoreTicker().RemoveTicker(TickerHandle);
		TickerHandle.Reset();
	}

	bCapturing = false;

	// Restore original target before readback
	if (SavedCaptureComponent.Get())
	{
		SavedCaptureComponent->TextureTarget = SavedOriginalTarget.Get();
	}

	DoReadback();

	SavedCaptureComponent = nullptr;
	SavedOriginalTarget = nullptr;

	return false;
}

void FLCapture::DoReadback() const
{
	FRenderTarget* Resource = SavedOriginalTarget->GameThread_GetRenderTargetResource();
	if (!Resource)
	{
		if (PendingCallback)
		{
			PendingCallback(PendingSavePath);
		}
		return;
	}

	TArray<FColor> Pixels;
	if (!Resource->ReadPixels(Pixels))
	{
		if (PendingCallback)
		{
			PendingCallback(PendingSavePath);
		}
		return;
	}

	for (FColor& Pixel : Pixels)
	{
		Pixel.A = 255;
	}

	IImageWrapperModule& ImageWrapperModule = FModuleManager::LoadModuleChecked<IImageWrapperModule>(FName("ImageWrapper"));
	const TSharedPtr<IImageWrapper> ImageWrapper = ImageWrapperModule.CreateImageWrapper(EImageFormat::PNG);

	if (!ImageWrapper.IsValid() || !ImageWrapper->SetRaw(Pixels.GetData(), Pixels.Num() * sizeof(FColor), Width, Height, ERGBFormat::BGRA, 8))
	{
		if (PendingCallback)
		{
			PendingCallback(PendingSavePath);
		}
		return;
	}

	TArray<uint8> ImageData;
	const TArray64<uint8>& Compressed = ImageWrapper->GetCompressed();
	ImageData.SetNumUninitialized(Compressed.Num());
	FMemory::Memcpy(ImageData.GetData(), Compressed.GetData(), Compressed.Num());

	if (ImageData.Num() == 0)
	{
		if (PendingCallback)
		{
			PendingCallback(PendingSavePath);
		}
		return;
	}

	if (FFileHelper::SaveArrayToFile(ImageData, *PendingSavePath))
	{
		UE_LOG(LogTemp, Log, TEXT("LCapture: Saved to %s (%dx%d)"), *PendingSavePath, Width, Height);
	}
	else
	{
		UE_LOG(LogTemp, Error, TEXT("LCapture: Failed to save to %s"), *PendingSavePath);
	}

	if (PendingCallback)
	{
		PendingCallback(PendingSavePath);
	}
}
