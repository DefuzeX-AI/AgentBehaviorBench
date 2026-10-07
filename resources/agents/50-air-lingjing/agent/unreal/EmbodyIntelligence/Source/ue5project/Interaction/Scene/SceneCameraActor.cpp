#include "SceneCameraActor.h"

#include "CesiumGlobeAnchorComponent.h"
#include "GameFramework/SpringArmComponent.h"

ASceneCameraActor::ASceneCameraActor()
{

	SpringArm->TargetArmLength = 120000.0f;
	SpringArm->bDoCollisionTest = false;
	SpringArm->bUsePawnControlRotation = true;
	SpringArm->bEnableCameraLag = true;
	SpringArm->bEnableCameraRotationLag = true;
	SpringArm->CameraRotationLagSpeed = 3.0f;

	GlobeAnchor = CreateDefaultSubobject<UCesiumGlobeAnchorComponent>(TEXT("CesiumGlobeAnchor"));
}

void ASceneCameraActor::OnScrollUp()
{
	if (SpringArm)
	{
		SpringArm->TargetArmLength -= Speed;
	}
}

void ASceneCameraActor::OnScrollDown()
{
	if (SpringArm)
	{
		SpringArm->TargetArmLength += Speed;
	}
}
