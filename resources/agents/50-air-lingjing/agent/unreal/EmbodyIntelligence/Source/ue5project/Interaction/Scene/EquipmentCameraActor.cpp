#include "EquipmentCameraActor.h"

#include "GameFramework/SpringArmComponent.h"

AEquipmentCameraActor::AEquipmentCameraActor()
{

	SpringArm->TargetArmLength = 1000.0f;
	SpringArm->bDoCollisionTest = false;
	SpringArm->bEnableCameraLag = true;
	SpringArm->bEnableCameraRotationLag = true;
	SpringArm->CameraRotationLagSpeed = 3.0f;

	SpringArm->bUsePawnControlRotation = true;
}

void AEquipmentCameraActor::OnScrollUp()
{
	if (SpringArm)
	{

		SpringArm->TargetArmLength = FMath::Max(SpringArm->TargetArmLength - Speed, 100.0);
	}
}

void AEquipmentCameraActor::OnScrollDown()
{
	if (SpringArm)
	{
		SpringArm->TargetArmLength += Speed;
	}
}
