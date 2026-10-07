// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "EquipmentActor.h"
#include "DroneActor.generated.h"

/*


*/
UCLASS()
class UE5PROJECT_API ADroneActor : public AEquipmentActor
{
	GENERATED_BODY()

public:
	ADroneActor();

protected:

	virtual FSColor GetTagWidgetColor() const override;

	virtual FString GetImageSaveSubdir() const override;
};
