#include "CameraController.h"

#include "EquipmentCameraActor.h"
#include "SceneCameraActor.h"

#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"

FCameraController* FCameraController::Get()
{
	static FCameraController Instance;
	return &Instance;
}

void FCameraController::Init(UWorld* InWorld)
{
	if (!InWorld)
	{
		return;
	}

	if (!EquipmentCamera.IsValid())
	{
		FActorSpawnParameters Params;
		Params.Name = TEXT("EquipmentCamera");
		Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		EquipmentCamera = InWorld->SpawnActor<AEquipmentCameraActor>(
			AEquipmentCameraActor::StaticClass(), FVector::ZeroVector, FRotator::ZeroRotator, Params);
	}

	if (!SceneCamera.IsValid())
	{
		FActorSpawnParameters Params;
		Params.Name = TEXT("SceneCamera");
		Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		SceneCamera = InWorld->SpawnActor<ASceneCameraActor>(
			ASceneCameraActor::StaticClass(), FVector::ZeroVector, FRotator::ZeroRotator, Params);
	}

	SwitchTo(ActiveType);
}

void FCameraController::SwitchTo(ECameraType InType)
{
	ActiveType = InType;

	AActor* Cam = GetActiveCamera();
	if (!Cam)
	{
		return;
	}

	UWorld* World = Cam->GetWorld();
	if (!World)
	{
		return;
	}

	APlayerController* PC = World->GetFirstPlayerController();
	if (!PC)
	{
		return;
	}

	PC->SetViewTarget(Cam);
	if (APawn* CamPawn = Cast<APawn>(Cam))
	{
		PC->UnPossess();
		PC->Possess(CamPawn);
	}

	PC->bShowMouseCursor = true;
}

void FCameraController::FocusOn(AActor* InTarget)
{
	if (!InTarget)
	{
		return;
	}



	SwitchTo(ECameraType::Equipment);

	AActor* Cam = GetActiveCamera();
	if (!Cam)
	{
		return;
	}

	Cam->AttachToActor(InTarget, FAttachmentTransformRules::KeepRelativeTransform);
	Cam->SetActorRelativeLocation(FVector::ZeroVector);
	Cam->SetActorRelativeRotation(FRotator::ZeroRotator);
}

AActor* FCameraController::GetActiveCamera() const
{
	switch (ActiveType)
	{
	case ECameraType::Equipment:
		return EquipmentCamera.Get();
	case ECameraType::Scene:
		return SceneCamera.Get();
	}
	return nullptr;
}
