// Fill out your copyright notice in the Description page of Project Settings.


#include "EquipmentActor.h"

#include "FEquipmentController.h"
#include "Engine/TextureRenderTarget2D.h"
#include "ue5project/Core/DataManager.h"
#include "ue5project/Interaction/UserInterface/Equipment/EquipmentWidgetController.h"
#include "ue5project/Interaction/UserInterface/SpaceWidget/TagWidget.h"
#include "ue5project/Net/HttpHelper/LUploaderManager.h"
#include "ue5project/Scene/Capture/LCapture.h"
#include "ue5project/Scene/Task/TaskMatrixController.h"
#include "ue5project/Scene/Task/TaskPointActor.h"
#include "ue5project/Interaction/Scene/CameraController.h"


AEquipmentActor::AEquipmentActor()
{
	PrimaryActorTick.bCanEverTick = true;

//	SceneComponent = CreateDefaultSubobject<USceneComponent>(TEXT("SceneComponent"));
//	RootComponent = SceneComponent;
}

void AEquipmentActor::BeginPlay()
{
	Super::BeginPlay();

	FrontRenderTarget = NewObject<UTextureRenderTarget2D>();
	FrontRenderTarget->InitCustomFormat(1024, 768, PF_B8G8R8A8, false);
	FrontRenderTarget->UpdateResourceImmediate(true);
	TopdownRenderTarget = NewObject<UTextureRenderTarget2D>();
	TopdownRenderTarget->InitCustomFormat(1024, 768, PF_B8G8R8A8, false);
	TopdownRenderTarget->UpdateResourceImmediate(true);
}

void AEquipmentActor::InitEquipment(const FEquipmentInfo& InEquipmentInfo)
{
	EquipmentInfo = InEquipmentInfo;

	if (TagWidget.IsValid())
	{
		TagWidget->SetWidgetType(STagWidget::EWidgetType::Equipment);
	}

	InitTagWidget(GetTagWidgetColor(), EquipmentInfo.EquipmentId);

	BlueprintInit();
}

FEquipmentInfo AEquipmentActor::GetEquipmentInfo() const
{
	return EquipmentInfo;
}

void AEquipmentActor::Capture(const FPhotoTaskInfo& InTaskInfo, USceneCaptureComponent2D* CaptureComponent,
                              const int32 SizeX, const int32 SizeY)
{
	FCaptureInfo CaptureInfo;
	CaptureInfo.UploadUrl = InTaskInfo.UploadUrl;
	CaptureInfo.Fields = InTaskInfo.Fields;
	CaptureInfo.FileField = InTaskInfo.FileField;

	CaptureInfo.CaptureComponent = CaptureComponent;
	CaptureInfo.Index = ++PhotoTaskIndex;
	CaptureInfo.SavePath = GetImageSaveDir() / InTaskInfo.PhotoId + TEXT(".png");
	CaptureInfo.LCapture = FLCapture::Create();

	CaptureInfo.SizeX = SizeX;
	CaptureInfo.SizeY = SizeY;



	const bool bWasIdle = CaptureList.IsEmpty();
	CaptureList.Add(CaptureInfo);
	if (bWasIdle)
	{
		ExecuteCapture(CaptureInfo);
	}
}

void AEquipmentActor::ExecuteCapture(const FCaptureInfo& InCaptureInfo)
{
	InCaptureInfo.LCapture->Capture(InCaptureInfo.CaptureComponent, InCaptureInfo.SizeX, InCaptureInfo.SizeY, InCaptureInfo.SavePath, [this, InCaptureInfo](const FString& InPath)
	{
		OnCaptureComplete(InCaptureInfo);
	});
}

void AEquipmentActor::OnCaptureComplete(const FCaptureInfo& InCaptureInfo)
{
	CaptureList.Remove(InCaptureInfo);



	const TSharedPtr<FLUploader> Uploader = FLUploaderManager::Get().CreateUploader();
	FLUploadFileEntry FileEntry;
	FileEntry.FileField = InCaptureInfo.FileField;
	FileEntry.FilePath = InCaptureInfo.SavePath;
	FileEntry.ContentType = TEXT("image/png");
	Uploader->OnUploadComplete().AddUObject(this, &AEquipmentActor::OnUploadComplete);
	Uploader->OnUploadComplete().AddLambda([FileEntry](const bool bSucceed, const FString& InMessage,
		const TSharedPtr<FLUploader>& InUploader)
	{
		if (IFileManager& FileManager = IFileManager::Get();
			FileManager.FileExists(*FileEntry.FilePath))
		{
			FileManager.Delete(*FileEntry.FilePath);
		}
	});
	TMap<FString, FString> Fields;
	TSharedPtr<FJsonObject> JsonObject;
	if (const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(InCaptureInfo.Fields);
		FJsonSerializer::Deserialize(Reader, JsonObject) && JsonObject.IsValid())
	{
		for (const auto& Pair : JsonObject->Values)
		{
			if (FString Value;
				Pair.Value->TryGetString(Value))
			{
				Fields.Add(Pair.Key, Value);
			}
		}
	}
	Uploader->Upload(InCaptureInfo.UploadUrl, {FileEntry}, Fields);


	if (!CaptureList.IsEmpty())
	{
		ExecuteCapture(CaptureList[0]);
	}
}

void AEquipmentActor::OnUploadComplete(const bool bSucceed, const FString& InMessage,
	const TSharedPtr<FLUploader>& InUploader) const
{
	if (!GEngine)
	{
		return;
	}
	if (bSucceed)
	{
		GEngine->AddOnScreenDebugMessage(-1, 10.f, FColor::Green,
			FString::Printf(TEXT("AEquipmentActor: %s Upload Succeed"), *EquipmentInfo.EquipmentId));
	}
	else
	{
		GEngine->AddOnScreenDebugMessage(-1, 10.f, FColor::Yellow,
			FString::Printf(TEXT("AEquipmentActor: %s Upload Failed, Message: %s"), *EquipmentInfo.EquipmentId, *InMessage));
	}
}

FString AEquipmentActor::GetImageSaveDir() const
{
	const FString SaveDir = FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir()) / TEXT("Capture") / GetImageSaveSubdir() / EquipmentInfo.EquipmentId;
	return SaveDir;
}

FSColor AEquipmentActor::GetTagWidgetColor() const
{

	switch (EquipmentInfo.Type)
	{
	case EEquipmentType::Drone:
		return FSColor(255, 179, 0, 0.5f);
	case EEquipmentType::Car:
		return FSColor(0, 179, 153, 0.5f);
	case EEquipmentType::Dog:
		return FSColor(0, 26, 255, 0.5f);
	case EEquipmentType::Ship:
		return FSColor(255, 0, 255, 0.5f);
	default:
		return FSColor(255, 255, 255, 0.5f);
	}
}

FString AEquipmentActor::GetImageSaveSubdir() const
{

	switch (EquipmentInfo.Type)
	{
	case EEquipmentType::Drone:
		return TEXT("Drone");
	case EEquipmentType::Car:
		return TEXT("Car");
	case EEquipmentType::Dog:
		return TEXT("Dog");
	default:
		return TEXT("");
	}
}

void AEquipmentActor::SwitchCameraTarget()
{
	FCameraController::Get()->FocusOn(this);
	FEquipmentWidgetController::Get()->CreateEquipmentWidget(EquipmentInfo.EquipmentId);
}

void AEquipmentActor::SnapGround()
{
	const FVector&& StartLocation = GetActorLocation();
	const FVector&& UpDirection = GetActorUpVector();
	const FVector&& EndLocation = StartLocation - 10000.0 * UpDirection;
	if (FHitResult HitResult;
		GetWorld()->LineTraceSingleByChannel(HitResult, StartLocation, EndLocation, ECC_Visibility))
	{
		SetActorLocation(HitResult.Location);


		const FRotator NewRotation = FRotationMatrix::MakeFromZX(HitResult.Normal, GetActorForwardVector()).Rotator();
		SetActorRotation(NewRotation);
	}
}

FVector AEquipmentActor::TraceLocation(const FVector& InLocation) const
{
	const FVector&& UpDirection = GetActorUpVector();
	const FVector&& EndLocation = InLocation - 10000.0 * UpDirection;
	if (FHitResult HitResult;
		GetWorld()->LineTraceSingleByChannel(HitResult, InLocation, EndLocation, ECC_Visibility))
	{
		return HitResult.Location;
	}
	return InLocation;
}
